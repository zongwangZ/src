# ec.yaml 配置项说明

```yaml
env: ec  # 环境的名称
env_args:  # 环境的配置项
  bandwidth: [2, 1, 0.1]  # 轻载，中载，重载情况下，带宽的大小
  cc: 4  # TCC 的计算速率
  cl: 1  # Edge Server 的计算速率
  max_steps: 20  # 每一个 episode 包含的 step 数量
  n_actions: 2  # 每一个 agent 可能的 action 数量
  n_agents: 4  # agent 的总数
  observation_size: 2  # 每一个 agent 状态的大小
  prob: [0.25, 0.75, 1]  # 轻载，中载，重载对应概率，此时为：0.25, 0.5, 0.25
  seed: null
  sum_d: 10  # 任务总量
  task_proportion: [0.25, 0.25, 0.25, 0.25]  # 任务分配的比例

train_cc_cl_scale: false  #表示是否一次性训练 cc_cl_scale 中所有的 cc/cl 比例对应的不同模型
cc_cl_scale: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]  # cc/cl 的比例

train_light_load_prob: false  # 表示是否一次性训练 light_load_prob 中所有轻载概率对应的不同模型
light_load_prob: [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1]  # 轻载对应的不同概率

train_mid_load_prob: flase  # 表示是否一次性训练 mid_load_prob 中所有中载概率对应的不同的训练模型
mid_load_prob: [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1]  # 中载对应的不同概率

train_weight_load_prob: false  # 表示是否一次性训练 weight_load_prob 中所有重载概率对应的不同的训练模型
weight_load_prob: [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1]  # 重载对应的不同概率

t_max: 80000  # 模型训练的总 step 数量

gen_data_cc_cl: false  # 表示是否一次性生成针对不同 cc/cl 比例，以及不同算法对应的最大期望任务
# cc_cl_checkpoint_path: []  # 通过参数 train_cc_cl_scale 和 cc_cl_scale 训练的模型名称列表

gen_data_light_load: false  # 表示是否一次性生成针对不同轻载概率，以及不同算法对应的最大期望任务
light_load_checkpoint_path: []  # 通过参数 train_light_load_prob 和 light_load_prob 训练的模型名称列表

gen_data_mid_load: true  # 表示是否一次性生成针对不同中载概率，以及不同算法对应的最大期望任务
# mid_load_checkpoint_path: []  # 通过参数 train_mid_load_prob 和 mid_load_prob 训练的模型名称列表

gen_data_weight_load: false  # 表示是否一次性生成针对不同重载概率，以及不同算法对应的最大期望任务
weight_load_checkpoint_path: []  # 通过 train_weight_load_prob 和 weight_load_prob 训练的模型名称列表

gen_t_max: 6000  # 生成最大期望任务数据时，每一次测试的数据量

# 生成相应的图
plot_cc_cl_scale: false
plot_light_load: false
plot_mid_load: false
plot_weight_load: false

mid_load_checkpoint_path: [qmix__2020-03-14_14-21-20, qmix__2020-03-14_14-25-33, qmix__2020-03-14_14-29-42,
  qmix__2020-03-14_14-33-45, qmix__2020-03-14_14-37-45, qmix__2020-03-14_14-41-45,
  qmix__2020-03-14_14-45-49, qmix__2020-03-14_14-49-52, qmix__2020-03-14_14-54-07,
  qmix__2020-03-14_14-58-13, qmix__2020-03-14_15-02-14]

cc_cl_checkpoint_path: [qmix__2020-03-14_10-06-01, qmix__2020-03-14_10-10-32, qmix__2020-03-14_10-15-23,
  qmix__2020-03-14_10-21-51, qmix__2020-03-14_10-26-35, qmix__2020-03-14_10-31-36,
  qmix__2020-03-14_10-36-41, qmix__2020-03-14_10-41-34, qmix__2020-03-14_10-46-16,
  qmix__2020-03-14_10-50-37]

cc_cl_checkpoint_path: [qmix__2020-03-17_09-52-13, qmix__2020-03-17_09-57-39, qmix__2020-03-17_10-03-14,
  qmix__2020-03-17_10-08-48, qmix__2020-03-17_10-14-26, qmix__2020-03-17_10-20-19,
  qmix__2020-03-17_10-26-06, qmix__2020-03-17_10-32-01, qmix__2020-03-17_10-38-17,
  qmix__2020-03-17_10-44-39, qmix__2020-03-17_10-50-15, qmix__2020-03-17_10-56-05,
  qmix__2020-03-17_11-03-48, qmix__2020-03-17_11-11-23, qmix__2020-03-17_11-18-24,
  qmix__2020-03-17_11-25-12, qmix__2020-03-17_11-31-37, qmix__2020-03-17_11-38-24,
  qmix__2020-03-17_11-44-35, qmix__2020-03-17_11-50-25, qmix__2020-03-17_11-56-58,
  qmix__2020-03-17_12-04-11, qmix__2020-03-17_12-09-30]
cc_cl_scale: [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000, 2000, 3000, 4000,
  5000, 6000, 7000, 8000, 9000, 10000, 20000, 30000, 40000, 50000]
```