import datetime
import os
import pprint
import time
import threading
import torch as th
from types import SimpleNamespace as SN
from utils.logging import Logger
from utils.timehelper import time_left, time_str
from os.path import dirname, abspath

from learners import REGISTRY as le_REGISTRY
from runners import REGISTRY as r_REGISTRY
from controllers import REGISTRY as mac_REGISTRY
from components.episode_buffer import ReplayBuffer
from components.transforms import OneHot
from envs.ec.expected_reward import ExpectedReward

from envs.wsn.result_analyzer import reward_result, plot_result

import numpy as np
import copy

from envs.ec.modify_yaml import ModifyYAML


def run(_run, _config, _log):
    # check args sanity
    _config = args_sanity_check(_config, _log)

    args = SN(**_config)
    args.device = "cuda" if args.use_cuda else "cpu"

    # setup loggers
    logger = Logger(_log)

    _log.info("Experiment Parameters:")
    experiment_params = pprint.pformat(_config,
                                       indent=4,
                                       width=1)
    _log.info("\n\n" + experiment_params + "\n")

    # configure tensorboard logger
    unique_token = "{}__{}".format(args.name, datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S"))
    args.unique_token = unique_token
    if args.use_tensorboard:
        tb_logs_direc = os.path.join(dirname(dirname(abspath(__file__))), "results", "tb_logs")
        tb_exp_direc = os.path.join(tb_logs_direc, "{}").format(unique_token)
        logger.setup_tb(tb_exp_direc)

    # sacred is on by default
    logger.setup_sacred(_run)

    # Run and train
    run_sequential(args=args, logger=logger)

    # Clean up after finishing
    print("Exiting Main")

    print("Stopping all threads")
    for t in threading.enumerate():
        if t.name != "MainThread":
            print("Thread {} is alive! Is daemon: {}".format(t.name, t.daemon))
            t.join(timeout=1)
            print("Thread joined")

    print("Exiting script")

    # Making sure framework really exits
    os._exit(os.EX_OK)


def evaluate_sequential(args, runner):
    for _ in range(args.test_nepisode):
        runner.run(test_mode=True)

    if args.save_replay:
        runner.save_replay()

    runner.close_env()


def run_sequential(args, logger):
    # Init runner so we can get env info
    runner = r_REGISTRY[args.runner](args=args, logger=logger)

    # Set up schemes and groups here
    env_info = runner.get_env_info()
    args.n_agents = env_info["n_agents"]
    args.n_actions = env_info["n_actions"]
    args.state_shape = env_info["state_shape"]

    args.save_model = True  # 需要从外部设置

    # Default/Base scheme
    scheme = {
        "state": {"vshape": env_info["state_shape"]},
        "obs": {"vshape": env_info["obs_shape"], "group": "agents"},
        "actions": {"vshape": (1,), "group": "agents", "dtype": th.long},
        "avail_actions": {"vshape": (env_info["n_actions"],), "group": "agents", "dtype": th.int},
        "reward": {"vshape": (1,)},
        "terminated": {"vshape": (1,), "dtype": th.uint8},
    }
    groups = {
        "agents": args.n_agents
    }
    preprocess = {
        "actions": ("actions_onehot", [OneHot(out_dim=args.n_actions)])
    }

    buffer = ReplayBuffer(scheme, groups, args.buffer_size, env_info["episode_limit"] + 1,
                          preprocess=preprocess,
                          device="cpu" if args.buffer_cpu_only else args.device)

    # Setup multiagent controller here
    # ---------------------------------
    # 设置 multi-agent controller
    # ---------------------------------
    mac = mac_REGISTRY[args.mac](buffer.scheme, groups, args)

    # Give runner the scheme
    runner.setup(scheme=scheme, groups=groups, preprocess=preprocess, mac=mac)

    # Learner
    learner = le_REGISTRY[args.learner](mac, buffer.scheme, logger, args)

    if args.use_cuda:
        learner.cuda()

    # -------------------------
    # 如果 checkpoint_path 不为空，那么需要首先从 checkpoint_path 加载模型
    # -------------------------
    if args.checkpoint_path != "":

        timesteps = []
        timestep_to_load = 0

        #
        if not os.path.isdir(args.checkpoint_path):
            logger.console_logger.info("Checkpoint directiory {} doesn't exist".format(args.checkpoint_path))
            return

        # Go through all files in args.checkpoint_path
        for name in os.listdir(args.checkpoint_path):
            full_name = os.path.join(args.checkpoint_path, name)
            # Check if they are dirs the names of which are numbers
            if os.path.isdir(full_name) and name.isdigit():
                timesteps.append(int(name))

        if args.load_step == 0:
            # choose the max timestep
            timestep_to_load = max(timesteps)
        else:
            # choose the timestep closest to load_step
            timestep_to_load = min(timesteps, key=lambda x: abs(x - args.load_step))

        # ----------------------------
        # 从本地加载模型
        # 1. 设置模型路径： args.checkpoint_path 对应 config/default.yaml 中的 checkpoint_path 配置项
        # 2. 加载模型
        # ----------------------------
        model_path = os.path.join(args.checkpoint_path, str(timestep_to_load))

        logger.console_logger.info("Loading model from {}".format(model_path))
        learner.load_models(model_path)
        runner.t_env = timestep_to_load

        # ------------------------------
        # 如果 default.yaml 中 cal_max_expectation_tasks 参数为 true， 表示需要使用已经训练好的最优模型来进行最大期望任务量的计算，而不进行模型的训练。
        # ------------------------------
        if args.cal_max_expectation_tasks:
            cal_max_expectation_tasks(args, mac, learner, runner)
            return

        if args.evaluate or args.save_replay:
            evaluate_sequential(args, runner)
            return

    # start training
    episode = 0
    last_test_T = -args.test_interval - 1
    last_log_T = 0
    model_save_time = 0

    start_time = time.time()
    last_time = start_time

    logger.console_logger.info("Beginning training for {} timesteps".format(args.t_max))

    global_reward = []
    global_state = []
    file_path = os.path.join(os.path.dirname(__file__), "envs", "ec", "output", "train_reward.txt")
    state_path = os.path.join(os.path.dirname(__file__), "envs", "ec", "output", "train_state.txt")

    test_state = []
    test_reward = []
    test_state_path = os.path.join(os.path.dirname(__file__), "envs", "ec", "output", "test_state.txt")
    test_reward_path = os.path.join(os.path.dirname(__file__), "envs", "ec", "output", "test_reward.txt")

    while runner.t_env <= args.t_max:  # t_env ?

        # Run for a whole episode at a time
        episode_batch = runner.run(test_mode=False)  # runner.run() 返回的是一个回合的数据。
        global_reward += get_episode_reward(episode_batch.data.transition_data)  # 将每一个 step 的 reward 都记录下来
        global_state += get_episode_state(episode_batch.data.transition_data)  # 将每个 step 的 state 都记录下来

        # 保存测试模式下的 state, reward 数据。 隔 args.reward_period 进行测试，测试的 state 数量为 args.reward_period。
        if runner.t_env % args.reward_period == 0:
            print("---------------------------------测试模式中-----------------------------------------")
            for i in range(int(args.reward_period / 20)):
                episode_data = runner.run(test_mode=True)  # 执行测试模式
                test_state += get_episode_state(episode_data.data.transition_data)
                test_reward += get_episode_reward(episode_data.data.transition_data)

        buffer.insert_episode_batch(episode_batch)

        if buffer.can_sample(args.batch_size):
            episode_sample = buffer.sample(args.batch_size)

            # Truncate batch to only filled timesteps
            max_ep_t = episode_sample.max_t_filled()
            episode_sample = episode_sample[:, :max_ep_t]

            if episode_sample.device != args.device:
                episode_sample.to(args.device)

            learner.train(episode_sample, runner.t_env, episode)

        # Execute test runs once in a while
        n_test_runs = max(1, args.test_nepisode // runner.batch_size)
        if (runner.t_env - last_test_T) / args.test_interval >= 1.0:

            logger.console_logger.info("t_env: {} / {}".format(runner.t_env, args.t_max))
            logger.console_logger.info("Estimated time left: {}. Time passed: {}".format(
                time_left(last_time, last_test_T, runner.t_env, args.t_max), time_str(time.time() - start_time)))
            last_time = time.time()

            last_test_T = runner.t_env
            for _ in range(n_test_runs):
                runner.run(test_mode=True)

        if args.save_model and (runner.t_env - model_save_time >= args.save_model_interval or model_save_time == 0):
            model_save_time = runner.t_env
            save_path = os.path.join(args.local_results_path, "models", args.unique_token, str(runner.t_env))
            # "results/models/{}".format(unique_token)
            os.makedirs(save_path, exist_ok=True)
            logger.console_logger.info("Saving models to {}".format(save_path))

            # learner should handle saving/loading -- delegate actor save/load to mac,
            # use appropriate filenames to do critics, optimizer states
            learner.save_models(save_path)

        episode += args.batch_size_run

        if (runner.t_env - last_log_T) >= args.log_interval:
            logger.log_stat("episode", episode, runner.t_env)
            logger.print_recent_stats()
            last_log_T = runner.t_env

    runner.close_env()
    save_state_reward(state_path, global_state)
    save_state_reward(file_path, global_reward)
    save_state_reward(test_state_path, test_state)
    save_state_reward(test_reward_path, test_reward)
    logger.console_logger.info("Finished Training")


def args_sanity_check(config, _log):
    # set CUDA flags
    # config["use_cuda"] = True # Use cuda whenever possible!
    if config["use_cuda"] and not th.cuda.is_available():
        config["use_cuda"] = False
        _log.warning("CUDA flag use_cuda was switched OFF automatically because no CUDA devices are available!")

    if config["test_nepisode"] < config["batch_size_run"]:
        config["test_nepisode"] = config["batch_size_run"]
    else:
        config["test_nepisode"] = (config["test_nepisode"] // config["batch_size_run"]) * config["batch_size_run"]

    return config


def save_state_reward(path, data):
    with open(path, "a") as f:
        np.savetxt(f, data)


def cal_max_expectation_tasks(args, mac, learner, runner):
    """
    加载已经训练好的模型，来生成 state-action-reward 数据，用来评价训练好的模型
    :param args:
    :param mac:
    :param learner:
    :param runner:
    :return:
    """
    algs_modify = ModifyYAML(os.path.join(os.path.dirname(__file__), "config", "algs", "qmix.yaml"))
    algs_modify.data["epsilon_finish"] = 0
    algs_modify.dump()

    modify = ModifyYAML(os.path.join(os.path.dirname(__file__), "config", "envs", "ec.yaml"))
    global_state = []
    global_action = []
    global_reward = []
    episode = int(modify.data["gen_t_max"]/modify.data["env_args"]["max_steps"])
    for i in range(episode):
        episode_batch = runner.run(test_mode=False)
        episode_data = episode_batch.data.transition_data
        global_state += get_episode_state(episode_data)
        global_action += get_episode_action(episode_data)
        global_reward += get_episode_reward(episode_data)

    expected_reward = ExpectedReward(global_state, global_reward).get_expected_reward()

    label = get_label(modify)
    file_path = os.path.join(os.path.dirname(__file__), "envs", "ec", "output", "rl_" + label + ".txt")
    with open(file_path, "a") as f:
        f.write(str(expected_reward) + "\n")


def get_label(modify):
    if modify.data["gen_data_cc_cl"] is True:
        return "cc_cl"
    elif modify.data["gen_data_light_load"] is True:
        return "light_load"
    elif modify.data["gen_data_mid_load"] is True:
        return "moderate_load"
    elif modify.data["gen_data_weight_load"] is True:
        return "heavy_load"
    else:
        return "policy_reward"


def get_episode_state(episode_data):
    global_state = []
    state = episode_data['state'].detach().numpy().tolist()[0][:-1]
    for temp in state:
        mid_res = []
        for item in temp:
            mid_res.append(round(item, 5))
        global_state.append(mid_res)
    return copy.deepcopy(global_state)


def get_episode_action(episode_data):
    global_action = []
    actions = episode_data['actions'].detach().numpy().tolist()[0][:-1]
    for action in actions:
        mid_res = []
        for item in action:
            mid_res.append(item[0])
        global_action.append(mid_res)
    return copy.deepcopy(global_action)


def get_episode_reward(episode_data):
    global_reward = []
    reward = episode_data['reward'].detach().numpy().tolist()[0][:-1]
    for item in reward:
        global_reward.append(item[0])
    return copy.deepcopy(global_reward)