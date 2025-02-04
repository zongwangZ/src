import numpy as np
from numpy.linalg import matrix_rank as rank, inv as inverse
from numpy.linalg import solve
from matplotlib import pyplot as plt
import time
import sys
import os
from matplotlib import font_manager
from src.envs.ec.data_processor import DataSaver


class Topology:
    # 定义topo
    def __init__(self,
                 var_vector=np.array([5, 5, 5, 5, 5]),
                 matrix=np.array([[1, 0, 1, 1, 0],
                                  [1, 0, 1, 0, 1],
                                  [0, 1, 1, 1, 0],
                                  [0, 1, 1, 0, 1]]),
                 node_matrix=np.array([[1, 0, 0, 0, 1, 0],
                                       [1, 0, 0, 0, 0, 1],
                                       [0, 1, 0, 0, 1, 0],
                                       [0, 1, 0, 0, 0, 1]]),
                 monitor_vector=np.array([1, 1, 0, 0, 1, 1]), way="FIM"
                 ):
        """
        :param matrix 测量矩阵
        [[1,0,1,1,0],
        [1,0,1,0,1],
        [0,1,1,1,0],
        [0,1,1,0,1]]
        :param node_matrix
        [[1,0,0,0,1,0],
        [1,0,0,0,0,1],
        [0,1,0,0,1,0],
        [0,1,0,0,0,1]]
        :param monitor_vector 监控节点
        [1,1,0,0,1,1]
        :param var_vector 链路时延方差向量
        [6, 2, 5, 2, 4]
        """
        self.way = way
        # print("测量方式：",self.way)
        if self.way == "Direct":
            self.var_vector = var_vector
            self.reduced_matrix = self.measure_matrix = np.array([
                [1, 0, 0, 0, 0],
                [0, 1, 0, 0, 0],
                [0, 0, 1, 0, 0],
                [0, 0, 0, 1, 0],
                [0, 0, 0, 0, 1],
            ])
            self.proportion = self.get_direct_proportion()
            self.H_x = self.get_H_x()
        else:
            self.matrix = matrix
            self.node_matrix = node_matrix
            self.monitor_vector = monitor_vector
            self.var_vector = var_vector
            # self.proportion = self.get_proportion()
            self.proportion = self.get_real_proportion()
            self.H_x = self.get_H_x()

    def get_extend_matrix(self):
        """
        获取扩展测量矩阵,返回扩展的测量矩阵
        :return:
        """
        extend_matrix = np.copy(self.matrix)
        len = self.matrix.shape[0]
        y_array = np.empty(shape=(0, 2), dtype=int)  # 记录y_ij
        for i in range(len):
            y_array = np.append(y_array, np.array([int(i + 1), int(i + 1)]).reshape(1, 2), axis=0)

        for index in range(len):
            for j in range(index + 1, len):
                y_array = np.append(y_array, np.array([index + 1, j + 1]).reshape(1, 2), axis=0)
                extend_matrix = np.vstack((extend_matrix, (self.matrix[index]) & (self.matrix[j])))
        # print(extend_matrix)
        # print(y_array)
        return extend_matrix, y_array

    def matrix_reduction(self, hatR, hatY):
        """
        对测量矩阵规约，返回规约的矩阵和对应Y
        :return:
        """
        dotR = []
        dotY = np.empty(shape=[0, 2])
        C = np.empty(shape=[0, 1])
        while rank(dotR) != rank(hatR):
            rank_dotR = rank(dotR)
            if rank_dotR == 0:
                dotR = np.empty(shape=[0, hatR.shape[1]])
            # 取出最小的行和
            if C.shape[0] == 0:
                index = list(range(hatR.shape[0]))
            else:
                index = list(
                    set(range(hatR.shape[0])).difference(set(C.flatten())))
            temp_hatR = hatR[index]
            k = index[np.random.choice(
                np.where(np.sum(temp_hatR, 1) == np.min(np.sum(temp_hatR, 1)))[0])]
            if rank(np.row_stack((dotR, hatR[k]))) > rank_dotR:
                dotR = np.row_stack((dotR, hatR[k]))
                dotY = np.row_stack((dotY, hatY[k]))
            C = np.row_stack((C, k))
        # print(dotR, dotY)
        return dotR, dotY

    def gen_delay(self, measure_matrix, path_scale, total_nums):
        """
        生成链路时延,生成路径时延，返回测量Y的值
        :param measure_matrix 规约之后的测量矩阵
        :param path_scale 探测包的数量. [0.2, 0.2, 0.2, 0.2, 0.2]
        :param total_nums
        :return:
        """
        assert isinstance(measure_matrix, np.ndarray)
        assert type(total_nums) == int

        cov = []

        for path_index, scale in enumerate(path_scale):
            delay = []
            path_prob_nums = int(total_nums * scale)
            # print("path ", (path_index + 1), " numbers of prob: ", path_prob_nums)
            for link_index in np.where(measure_matrix[path_index] == 1)[0]:
                link_delay = []
                for _ in range(path_prob_nums):
                    link_delay.append(np.random.normal(0, np.sqrt(self.var_vector[link_index])))
                # print("link delay of link ", (link_index + 1), ": ", link_delay)
                delay.append(link_delay)
            # print("all link delay: ", delay)

            path_delay = np.zeros(path_prob_nums)
            for link_delay in delay:
                path_delay = np.add(path_delay, link_delay)
            # print("path delay: ", path_delay)

            delay_cov = np.var(path_delay)
            # print("path delay covariance: ", delay_cov)
            cov.append(delay_cov)

        # print("all path delay covariance", cov)
        return cov

    def cal_phi(self, Y_value, reduced_matrix):
        """
        \mathcal{A}_i(\boldsymbol{\theta}) = 2(\sum_{l \in p_i} \theta_l)^2 \sum_{k=1}^{|L|}b_{k,i}^2
        \phi_{i}=\frac{\sqrt{\mathcal{A}_{i}(\boldsymbol{\theta})}}{\sum_{j=1}^{|L|} \sqrt{\mathcal{A}_{j}(\boldsymbol{\theta})}}
        计算A_i,计算\phi_i,
        :return:
        """
        assert isinstance(Y_value, list)
        # assert isinstance(reduced_matrix,np.array)
        # 求规约矩阵的逆矩阵
        inverse_matrix = inverse(reduced_matrix)
        A = []
        Phi = []
        for i in range(len(Y_value)):
            # 取出逆矩阵的列平方和
            sum_col = 0
            for k in range(len(inverse_matrix[:, i])):
                sum_col += inverse_matrix[:, i][k] ** 2
            value = 2 * (Y_value[i] ** 2) * sum_col
            A.append(value)
        # 计算 A 的平方根和
        sum_A = 0
        for i in range(len(A)):
            sum_A += np.sqrt(A[i])
        for i in range(len(Y_value)):
            Phi.append(np.sqrt(A[i]) / sum_A)
        # print("the sum of phi:",sum(Phi))
        return Phi

    def cal_proportions(self, phi_i, dot_y):
        """
        计算H，返回监测节点的比例
        :return:
        """
        # 计算pi的权重
        p_i_w = np.empty(shape=(1, 0))
        for i in range(self.node_matrix.shape[0]):  # 根据路径遍历
            y_i_index = set((np.argwhere(dot_y == i + 1)[:, 0]))  # <h_ij或者h_ji>返回dot_y中元素为i+1的行坐标(与顶点i+1有关的路径）
            sum = 0
            for j in y_i_index:  # 对相关路径权重求和
                sum += phi_i[j]
            sum = sum / 2
            p_i_w = np.append(p_i_w, sum)  # 添加路径权重
        # print(p_i_w)

        # 计算节点的权重
        nodes = np.argwhere(self.monitor_vector == 1).flatten() + 1  # 获取所有节点编号
        nodes_i_w = np.empty(shape=(1, 0))
        for i in list(nodes):  # 对每一个节点遍历
            sum = 0
            i_line = set(np.argwhere(self.node_matrix[:, i - 1] == 1).flatten() + 1)  # 找出和顶点i有关的路径
            for j in i_line:
                sum += p_i_w[j - 1]
            nodes_i_w = np.append(nodes_i_w, sum / 2)
        # print(nodes_i_w)
        return nodes_i_w

    def get_proportion(self):
        """
        调用函数取得比列
        :return:
        """
        hatR, hatY = self.get_extend_matrix()
        dotR, dotY = self.matrix_reduction(hatR, hatY)
        self.reduced_matrix = dotR
        Y_value = self.gen_delay(dotR, [0.2, 0.2, 0.2, 0.2, 0.2], 10000)
        Phi = self.cal_phi(Y_value, dotR)
        self.Phi = Phi
        proportion = self.cal_proportions(Phi, dotY)
        return proportion

    def get_real_proportion(self):
        hatR, hatY = self.get_extend_matrix()
        dotR, dotY = self.matrix_reduction(hatR, hatY)
        self.reduced_matrix = dotR
        Y_value = list(np.dot(dotR, self.var_vector))
        Phi = self.cal_phi(Y_value, dotR)
        self.Phi = Phi
        proportion = self.cal_proportions(Phi, dotY)
        return proportion

    def get_direct_proportion(self):
        Y_value = list(np.dot(self.measure_matrix, self.var_vector))
        self.Phi = self.cal_phi(Y_value, self.measure_matrix)
        proportion = []
        return []

    def get_H_x(self):
        """
        reduced_matrix =
        [[0. 0. 1. 0. 0.],
        [0. 1. 1. 0. 0.],
        [0. 0. 1. 1. 0.],
        [0. 0. 1. 0. 1.],
        [1. 0. 1. 0. 0.]]
        Y=RX   就是经过 algorithm 1 得到的 R 和Y。
        Y=RX  ==>   H_x = H_y^{T} R / (sum H_y) 来计算得到。H_y^{T} 是 列向量 H_y 的装置

        H_y 就是 FIM 确定的 各个相关测量数据 所占的比例

        :return:
        """
        temp = np.dot(np.array(self.Phi), self.reduced_matrix) / np.sum(np.array(self.Phi))
        return temp / np.sum(temp)

    def cal_measured_link_parameter(self, path_cov):
        """
        计算测量的路径方差
        :param path_cov:
        :return:
        """
        assert isinstance(path_cov, list)
        measured_X = solve(self.reduced_matrix, path_cov)
        return measured_X


def region_error():
    """
   画出均匀分布区间和估计误差

   Fig 1.a 所有的链路的时延方差 服从均匀分布（区间长度从 0 开始；0 区间长度表示所有链路具有相同的时延方差），x-axis：区间的长度，y-axis： NT的估计误差 （所有 链路的 平均估计误差）；重复实验k次

    :return:
    """
    # 参数设置
    parameter = {
        "regions": list(range(0, 8 + 2, 2)),
        "start_point": 5,
        "exp_times": 100,  # 测量的重复次数
        "n": 100,  # 生成方差的次数
        "average_proportion": [0.2, 0.2, 0.2, 0.2, 0.2],
        "sum_data": 10000,
    }
    # 保存参数
    func_name = sys._getframe().f_code.co_name
    data_saver = DataSaver(func_name)
    data_saver.add_item("parameter", parameter)
    x_axis = regions = parameter["regions"]  # 设定均匀分布的区间长度值
    start_point = parameter["start_point"]  # 设置均匀分布的中间值
    exp_times = parameter["exp_times"]
    n = parameter["n"]
    average_proportion = parameter["average_proportion"]
    # 数据总量
    sum_data = parameter["sum_data"]
    y1_axis = []
    y2_axis = []
    for region in regions:
        fim_MES = 0
        average_MSE = 0
        for i in range(n):
            # 1.均匀分布生成方差
            var_vector = np.random.randint(start_point, start_point + region + 1, 5)
            # 2.构建topo
            topo = Topology(var_vector)

            fim_mse = 0
            average_mse = 0
            for j in range(exp_times):
                # 3.生成数据，并且推断
                # FIM值
                fim_cov = topo.gen_delay(topo.reduced_matrix, topo.Phi, sum_data)
                fim_measured_X = topo.cal_measured_link_parameter(fim_cov)
                average_cov = topo.gen_delay(topo.reduced_matrix, average_proportion, sum_data)
                average_measured_X = topo.cal_measured_link_parameter(average_cov)

                # 计算mse
                # fim_mse += np.mean((np.array(fim_measured_X) - var_vector)**2)/exp_times
                fim_mse += np.dot((np.array(fim_measured_X) - var_vector) ** 2, topo.H_x) / exp_times

                average_mse += np.mean((np.array(average_measured_X) - var_vector) ** 2) / exp_times
            fim_MES += fim_mse / n
            average_MSE += average_mse / n
        y1_axis.append(fim_MES)
        y2_axis.append(average_MSE)
    data_saver.add_item("fim_MSE", y1_axis)
    data_saver.add_item("average_MSE", y2_axis)

    plt.figure()
    plt.plot(regions, y1_axis, label="Fim", marker=".", color="black")
    plt.plot(regions, y2_axis, label="Average", marker="o", color="red")
    plt.xlabel("scale")
    plt.ylabel("mse")
    # plt.ylim([0,1])
    plt.legend()
    plt.title("the variation of scale vs MSE")
    dir = os.path.join(os.getcwd(), "data", func_name)
    fig_name = dir + "/" + func_name + "_" + time.strftime("%Y-%m-%d_%H-%M-%S") + ".png"
    if not os.path.exists(dir):
        os.makedirs(dir)
    plt.savefig(fig_name)
    plt.show()
    plt.close()
    data_saver.to_file()


def uniform_fim():
    """
    按照 Fig 1.a 选定合适的 链路时延方差
    Fig 1.b x-axis: k 步逼近，y-axis： NT的估计误差 （所有 链路的 平均估计误差）；重复实验k次

    最直接的一个方案：分成 k 步来逼近，每步按照  (最优比例-均匀比例)/k  来修正上一步的比例
    是的哈，按照上面的式子，你肯定最终 是收敛到最优方案的
    """
    parameter = {
        "var_vector": [5, 8, 16, 12, 10],  # 由图1 a中
        "average_proportion": [0.2, 0.2, 0.2, 0.2, 0.2],
        "k_step": 10,
        "sum_data": 10000,
        "exp_times": 500
    }
    # 保存参数
    func_name = sys._getframe().f_code.co_name
    print(func_name, "is running at ", time.strftime("%Y-%m-%d_%H-%M-%S"))
    data_saver = DataSaver(func_name)
    data_saver.add_item("parameter", parameter)
    # 计算最优比例
    var_vector = parameter["var_vector"]
    topo = Topology(var_vector=var_vector)
    optimal_proportion = topo.Phi
    data_saver.add_item("FIM_proportion", optimal_proportion)
    # 平均比列
    average_proportion = parameter["average_proportion"]
    k_step = parameter["k_step"]  # 分多少次接近最优比列
    x_axis = list(range(k_step + 1))
    all_proportion = []
    for i in range(k_step):
        proportion = np.array(average_proportion) + (
                np.array(optimal_proportion) - np.array(average_proportion)) / k_step * i
        all_proportion.append(proportion.tolist())
    all_proportion.append(optimal_proportion)
    # 这里各个链路占的比例应该也从平均比例变化到H_x
    H_x_proportions = []
    for i in range(k_step):
        proportion = np.array(average_proportion) + (np.array(topo.H_x) - np.array(average_proportion)) / k_step * i
        H_x_proportions.append(proportion.tolist())
    H_x_proportions.append(topo.H_x.tolist())
    data_saver.add_item("data_proportion", all_proportion)
    data_saver.add_item("H_x_proportions", H_x_proportions)
    y_axis = []
    # 数据总量
    sum_data = parameter["sum_data"]
    exp_times = parameter["exp_times"]  # 实验重复次数
    for index, proportion in enumerate(all_proportion):
        print(index, time.strftime("%Y-%m-%d_%H-%M-%S"))
        mse = 0
        for _ in range(exp_times):
            cov = topo.gen_delay(topo.reduced_matrix, proportion, sum_data)
            measured_X = topo.cal_measured_link_parameter(cov)
            mse += np.dot((np.array(measured_X) - np.array(var_vector)) ** 2, H_x_proportions[index]) / exp_times
        y_axis.append(mse)

    # 画图
    print("x_axis:", x_axis)
    print("y_axis:", y_axis)
    plt.figure()
    plt.plot(x_axis, y_axis, marker="o", color="blue")
    plt.xlabel("step")
    plt.ylabel("MSE")
    plt.legend()
    plt.title("average proportion to FIM proportion")
    dir = os.path.join(os.getcwd(), "data", func_name)
    fig_name = dir + "/" + func_name + "_" + time.strftime("%Y-%m-%d_%H-%M-%S") + ".png"
    if not os.path.exists(dir):
        os.makedirs(dir)
    plt.savefig(fig_name)
    plt.show()
    plt.close()
    data_saver.add_item("x_axis", x_axis)
    data_saver.add_item("y_axis", y_axis)
    data_saver.to_file()


# def sum_data_influence():
#     parameter = {
#         "region":8,
#         "start_point":5,
#         "n":100,#生成方差的次数
#         "sum_data_range":[500,2000,5000,10000,50000],
#         "exp_times":100,#测量的重复次数
#     }
#     #保存参数
#     func_name = sys._getframe().f_code.co_name
#     data_saver = DataSaver(func_name)
#     data_saver.add_item("parameter", parameter)
#     #均匀分布的参数
#     region = parameter["region"]
#     start_point = parameter["start_point"]
#     #确定数据量变化的范围
#     x_axis = sum_data_range = parameter["sum_data_range"]
#     #确定产生方差的次数
#     n = parameter["n"]
#     #确定测量重复的次数
#     exp_times = parameter["exp_times"]
#     y_axis = []
#     for sum_data in sum_data_range:
#         MSE = 0
#         for i in range(n):
#             var_vector = np.random.randint(start_point, start_point+region+1, 5)
#             #计算最优比例
#             topo = Topology(var_vector)
#             optimal_proportion = topo.Phi
#             #测量
#             mse = 0
#             for j in range(exp_times):
#                 cov = topo.gen_delay(topo.reduced_matrix, optimal_proportion, sum_data)
#                 measured_X = topo.cal_measured_link_parameter(cov)
#                 mse += np.dot((np.array(measured_X) - np.array(var_vector)) ** 2,topo.H_x) / exp_times
#                 # mse += np.mean((np.array(measured_X) - np.array(var_vector)) ** 2) / exp_times
#             MSE += mse/n
#         y_axis.append(MSE)
#     # 画图
#     plt.figure()
#     plt.plot(x_axis, y_axis, marker="o", color="blue")
#     plt.xlabel("#data")
#     plt.ylabel("MSE")
#     plt.title("the influence of #data")
#     plt.legend()
#     dir = os.path.join(os.getcwd(), "data", func_name)
#     fig_name = dir + "/" + func_name + "_" + time.strftime("%Y-%m-%d_%H-%M-%S") + ".png"
#     if not os.path.exists(dir):
#         os.makedirs(dir)
#     plt.savefig(fig_name)
#     plt.show()
#     plt.close()
#     data_saver.add_item("x_axis",x_axis)
#     data_saver.add_item("y_axis", y_axis)
#     data_saver.to_file()


def cdf_mse():
    """
    选出Fig 1 中 区间长度为0，中间，最大共3个值：
    Fig 2,3,4  给出对应的 3副 CDF 统计图 ，x-axis: 估计误差（注意 这里是统计每条链路每一次得到的 估计误差），y-axis:估计误差的累积概率
    :return:
    """
    parameter = {
        # "regions": [0,10,20],
        "regions": [15],
        "start_point": 5,
        "n": 2000,  # 生成方差的次数
        "sum_data": 10000,
        "exp_times": 100,  # 测量的重复次数
    }
    # 保存参数
    func_name = sys._getframe().f_code.co_name
    data_saver = DataSaver(func_name)
    data_saver.add_item("parameter", parameter)
    # 均匀分布的参数,0，中间，最大
    regions = parameter["regions"]
    start_point = parameter["start_point"]
    # 确定产生方差的次数
    n = parameter["n"]
    # 确定测量重复的次数
    exp_times = parameter["exp_times"]
    # 产生的总数据量
    sum_data = parameter["sum_data"]
    for region in regions:
        print(region)
        MSE = np.empty(shape=[0, 5])
        for i in range(n):
            var_vector = np.random.randint(start_point, start_point + region + 1, 5)
            # 计算最优比例
            topo = Topology(var_vector)
            optimal_proportion = topo.Phi
            # 测量
            mse = np.array([0, 0, 0, 0, 0], dtype=float)
            for j in range(exp_times):
                cov = topo.gen_delay(topo.reduced_matrix, optimal_proportion, sum_data)
                measured_X = topo.cal_measured_link_parameter(cov)
                mse += (np.array(measured_X) - np.array(var_vector)) ** 2 / exp_times
            MSE = np.row_stack((MSE, mse))
        MSE_data = MSE.flatten()
        # 画CDF图
        plt.figure()
        plt.hist(MSE_data, cumulative=True, normed=True)
        plt.xlabel("MSE")
        plt.ylabel("CDF")
        # plt.title("the cdf ("+str(region)+")")
        plt.legend()
        dir = os.path.join(os.getcwd(), "data", func_name)
        fig_name = dir + "/" + func_name + "_" + str(region) + "_" + time.strftime("%Y-%m-%d_%H-%M-%S") + ".png"
        if not os.path.exists(dir):
            os.makedirs(dir)
        plt.savefig(fig_name)
        plt.show()
        plt.close()
        # 对MSE数据进行保存
        data_saver.add_item(str(region), MSE)
    data_saver.to_file()


def plot_result():
    x = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    y = [0.04315833534141526, 0.0435988569870744, 0.043925725970413665, 0.04300237543732725, 0.04314024095026359,
         0.04347379847806098,
         0.042743479500658065, 0.04233640474616092, 0.04202061611765972, 0.042920396591611606, 0.042868753494841705]
    font_path = "/usr/fonts/truetype/msttcorefonts/Times_New_Roman.ttf"
    prop = font_manager.FontProperties(fname=font_path)
    plt.rcParams["font.family"] = prop.get_name()
    plt.plot(x, y, label="random", marker="*")
    # plt.plot(x, all_local_max_expectation, label="all_local", marker=">")
    # plt.plot(x, all_offload_max_expectation, label="all_offload", marker="o")
    # plt.plot(x, rl_max_expectation, label="rl", marker="P")
    plt.title("avarage proportion to FIM proportion", fontsize=10)
    plt.xlabel("steps", fontsize=10)
    plt.ylabel("mean MSE", fontsize=10)
    plt.yticks(fontsize=10)
    plt.xticks(x, fontsize=10)
    plt.grid()
    plt.legend(fontsize=10)
    plt.show()


def sum_data_influence():
    parameter = {}
    # 保存参数
    func_name = sys._getframe().f_code.co_name
    data_saver = DataSaver(func_name)
    data_saver.add_item("parameter", parameter)
    # 均匀分布的参数
    region = parameter["region"]
    start_point = parameter["start_point"]
    # 确定数据量变化的范围
    x_axis = sum_data_range = parameter["sum_data_range"]
    # 确定产生方差的次数
    n = parameter["n"]
    # 确定测量重复的次数
    exp_times = parameter["exp_times"]
    y_axis = []
    for sum_data in sum_data_range:
        MSE = 0
        for i in range(n):
            var_vector = np.random.randint(start_point, start_point + region + 1, 5)
            # 计算最优比例
            topo = Topology(var_vector)
            optimal_proportion = topo.Phi
            # 测量
            mse = 0
            for j in range(exp_times):
                cov = topo.gen_delay(topo.reduced_matrix, optimal_proportion, sum_data)
                measured_X = topo.cal_measured_link_parameter(cov)
                mse += np.dot((np.array(measured_X) - np.array(var_vector)) ** 2, topo.H_x) / exp_times
                # mse += np.mean((np.array(measured_X) - np.array(var_vector)) ** 2) / exp_times
            MSE += mse / n
        y_axis.append(MSE)
    # 画图
    print("x_axis:", x_axis)
    print("y_axis:", y_axis)
    plt.figure()
    plt.plot(x_axis, y_axis, marker="o", color="blue")
    plt.xlabel("#data")
    plt.ylabel("MSE")
    plt.title("the influence of #data")
    plt.legend()
    dir = os.path.join(os.getcwd(), "data", func_name)
    fig_name = dir + "/" + func_name + "_" + time.strftime("%Y-%m-%d_%H-%M-%S") + ".png"
    if not os.path.exists(dir):
        os.makedirs(dir)
    plt.savefig(fig_name)
    plt.show()
    plt.close()
    data_saver.add_item("x_axis", x_axis)
    data_saver.add_item("y_axis", y_axis)
    data_saver.to_file()


def sum_data_influence_uniform():
    parameter = {
        "region": 8,
        "start_point": 5,
        "n": 100,  # 生成方差的次数
        "sum_data_range": [50000],
        "exp_times": 100,  # 测量的重复次数
    }
    # 保存参数
    func_name = sys._getframe().f_code.co_name
    data_saver = DataSaver(func_name)
    data_saver.add_item("parameter", parameter)
    # 均匀分布的参数
    region = parameter["region"]
    start_point = parameter["start_point"]
    # 确定数据量变化的范围
    x_axis = sum_data_range = parameter["sum_data_range"]
    # 确定产生方差的次数
    n = parameter["n"]
    # 确定测量重复的次数
    exp_times = parameter["exp_times"]
    y_axis = []
    for sum_data in sum_data_range:
        MSE = 0
        for i in range(n):
            var_vector = np.random.randint(start_point, start_point + region + 1, 5)
            # 计算最优比例
            topo = Topology(var_vector)
            uniform_proportion = [0.2, 0.2, 0.2, 0.2, 0.2]
            # 测量
            mse = 0
            for j in range(exp_times):
                cov = topo.gen_delay(topo.reduced_matrix, uniform_proportion, sum_data)
                measured_X = topo.cal_measured_link_parameter(cov)
                mse += np.dot((np.array(measured_X) - np.array(var_vector)) ** 2,
                              np.array(uniform_proportion)) / exp_times
                # mse += np.mean((np.array(measured_X) - np.array(var_vector)) ** 2) / exp_times
            MSE += mse / n
        y_axis.append(MSE)
    # 画图
    plt.figure()
    plt.plot(x_axis, y_axis, marker="o", color="blue")
    print("x_axis:", x_axis)
    print("y_axis:", y_axis)
    plt.xlabel("#probe")
    plt.ylabel("mean MSE")
    # plt.title("the influence of #probe")
    plt.legend()
    dir = os.path.join(os.getcwd(), "data", func_name)
    fig_name = dir + "/" + func_name + "_" + time.strftime("%Y-%m-%d_%H-%M-%S") + ".png"
    if not os.path.exists(dir):
        os.makedirs(dir)
    plt.savefig(fig_name)
    plt.show()
    plt.close()
    data_saver.add_item("x_axis", x_axis)
    data_saver.add_item("y_axis", y_axis)
    data_saver.to_file()


def region_error_direct():
    """
   画出均匀分布区间和估计误差

   Fig 1.a 所有的链路的时延方差 服从均匀分布（区间长度从 0 开始；0 区间长度表示所有链路具有相同的时延方差），x-axis：区间的长度，y-axis： NT的估计误差 （所有 链路的 平均估计误差）；重复实验k次

    :return:
    """
    # 参数设置
    parameter = {
        "regions": list(range(0, 20 + 2, 2)),
        "start_point": 5,
        "exp_times": 100,  # 测量的重复次数
        "n": 100,  # 生成方差的次数
        "sum_data": 10000,
    }
    # 保存参数
    func_name = sys._getframe().f_code.co_name
    print(func_name, " is running at ", time.strftime("%Y-%m-%d_%H-%M-%S"))
    data_saver = DataSaver(func_name)
    data_saver.add_item("parameter", parameter)
    x_axis = regions = parameter["regions"]  # 设定均匀分布的区间长度值
    start_point = parameter["start_point"]  # 设置均匀分布的中间值
    exp_times = parameter["exp_times"]
    n = parameter["n"]
    # 数据总量
    sum_data = parameter["sum_data"]
    y_axis = []
    for region in regions:
        print(region, time.strftime("%Y-%m-%d_%H-%M-%S"))
        Direct_mse = 0
        for i in range(n):
            # 1.均匀分布生成方差
            var_vector = np.random.randint(start_point, start_point + region + 1, 5)
            # 2.构建topo
            topo = Topology(var_vector=var_vector, way="Direct")

            direct_mse = 0
            for j in range(exp_times):
                # 3.生成数据，并且推断
                # FIM值
                direct_cov = topo.gen_delay(topo.reduced_matrix, topo.Phi, sum_data)
                direct_measured_X = topo.cal_measured_link_parameter(direct_cov)

                # 计算mse
                direct_mse += np.dot((np.array(direct_measured_X) - var_vector) ** 2, topo.H_x) / exp_times

            Direct_mse += direct_mse / n
        y_axis.append(Direct_mse)
    data_saver.add_item("Direct_mse", y_axis)

    plt.figure()
    plt.plot(regions, y_axis, label="Direct", marker=".", color="black")
    plt.xlabel("scale")
    plt.ylabel("MSE")
    # plt.ylim([0,1])
    plt.legend()
    # plt.title("the variation of scale vs MSE")
    dir = os.path.join(os.getcwd(), "data", func_name)
    fig_name = dir + "/" + func_name + "_" + time.strftime("%Y-%m-%d_%H-%M-%S") + ".png"
    if not os.path.exists(dir):
        os.makedirs(dir)
    plt.savefig(fig_name)
    plt.show()
    plt.close()
    data_saver.to_file()


def sum_data_influence_direct():
    parameter = {
        "region": 8,
        "start_point": 5,
        "n": 100,  # 生成方差的次数
        "sum_data_range": list(range(1000, 23000, 2000)),
        "exp_times": 100,  # 测量的重复次数
    }
    # 保存参数
    func_name = sys._getframe().f_code.co_name
    print(func_name, " is running at ", time.strftime("%Y-%m-%d_%H-%M-%S"))
    data_saver = DataSaver(func_name)
    data_saver.add_item("parameter", parameter)
    # 均匀分布的参数
    region = parameter["region"]
    start_point = parameter["start_point"]
    # 确定数据量变化的范围
    x_axis = sum_data_range = parameter["sum_data_range"]
    # 确定产生方差的次数
    n = parameter["n"]
    # 确定测量重复的次数
    exp_times = parameter["exp_times"]
    y_axis = []
    for sum_data in sum_data_range:
        print(sum_data, time.strftime("%Y-%m-%d_%H-%M-%S"))
        MSE = 0
        for i in range(n):
            var_vector = np.random.randint(start_point, start_point + region + 1, 5)
            # 计算最优比例
            topo = Topology(var_vector=var_vector, way="Direct")
            # 测量
            mse = 0
            for j in range(exp_times):
                cov = topo.gen_delay(topo.reduced_matrix, topo.Phi, sum_data)
                measured_X = topo.cal_measured_link_parameter(cov)
                mse += np.dot((np.array(measured_X) - np.array(var_vector)) ** 2, topo.H_x) / exp_times
            MSE += mse / n
        y_axis.append(MSE)
    # 画图
    print("x_axis:", x_axis)
    print("y_axis:", y_axis)
    plt.figure()
    plt.plot(x_axis, y_axis, marker="o", color="blue", label="Direct")
    plt.xlabel("#probe")
    plt.ylabel("MSE")
    # plt.title("the influence of #probe")
    plt.legend()
    dir = os.path.join(os.getcwd(), "data", func_name)
    fig_name = dir + "/" + func_name + "_" + time.strftime("%Y-%m-%d_%H-%M-%S") + ".png"
    if not os.path.exists(dir):
        os.makedirs(dir)
    plt.savefig(fig_name)
    plt.show()
    plt.close()
    data_saver.add_item("x_axis", x_axis)
    data_saver.add_item("y_axis", y_axis)
    data_saver.to_file()


def uniform_direct():
    """
    按照 Fig 1.a 选定合适的 链路时延方差
    Fig 1.b x-axis: k 步逼近，y-axis： NT的估计误差 （所有 链路的 平均估计误差）；重复实验k次

    最直接的一个方案：分成 k 步来逼近，每步按照  (最优比例-均匀比例)/k  来修正上一步的比例
    是的哈，按照上面的式子，你肯定最终 是收敛到最优方案的
    """
    parameter = {
        "var_vector": [5, 8, 16, 12, 10],  # 由图1 a中
        "average_proportion": [0.2, 0.2, 0.2, 0.2, 0.2],
        "k_step": 10,
        "sum_data": 10000,
        "exp_times": 500
    }
    # 保存参数
    func_name = sys._getframe().f_code.co_name
    print(func_name, "is running at ", time.strftime("%Y-%m-%d_%H-%M-%S"))
    data_saver = DataSaver(func_name)
    data_saver.add_item("parameter", parameter)
    # 计算最优比例,直接测量
    var_vector = parameter["var_vector"]
    direct_topo = Topology(var_vector=var_vector, way="Direct")
    direct_proportion = direct_topo.Phi
    data_saver.add_item("direct_proportion", direct_proportion)
    # 平均比列
    average_proportion = parameter["average_proportion"]
    k_step = parameter["k_step"]  # 分多少次接近最优比列
    x_axis = list(range(k_step + 1))
    all_proportion = []
    for i in range(k_step):
        proportion = np.array(average_proportion) + (
                np.array(direct_proportion) - np.array(average_proportion)) / k_step * i
        all_proportion.append(proportion.tolist())
    all_proportion.append(direct_proportion)
    # 这里各个链路占的比例应该也从平均比例变化到H_x
    H_x_proportions = []
    for i in range(k_step):
        proportion = np.array(average_proportion) + (
                np.array(direct_topo.H_x) - np.array(average_proportion)) / k_step * i
        H_x_proportions.append(proportion.tolist())
    H_x_proportions.append(direct_topo.H_x.tolist())
    data_saver.add_item("data_proportion", all_proportion)
    data_saver.add_item("H_x_proportions", H_x_proportions)
    y_axis = []
    # 数据总量
    sum_data = parameter["sum_data"]
    exp_times = parameter["exp_times"]  # 实验重复次数
    for index, proportion in enumerate(all_proportion):
        print(index, time.strftime("%Y-%m-%d_%H-%M-%S"))
        mse = 0
        for _ in range(exp_times):
            cov = direct_topo.gen_delay(direct_topo.reduced_matrix, proportion, sum_data)
            measured_X = direct_topo.cal_measured_link_parameter(cov)
            # mse += np.mean((np.array(measured_X) - np.array(var_vector))**2)/exp_times
            mse += np.dot((np.array(measured_X) - np.array(var_vector)) ** 2, H_x_proportions[index]) / exp_times
        y_axis.append(mse)
    print("x_axis:", x_axis)
    print("y_axis:", y_axis)
    # 画图
    plt.figure()
    plt.plot(x_axis, y_axis, marker="o", color="blue")
    plt.xlabel("step")
    plt.ylabel("MSE")
    plt.legend()
    plt.title("average proportion to FIM proportion")
    dir = os.path.join(os.getcwd(), "data", func_name)
    fig_name = dir + "/" + func_name + "_" + time.strftime("%Y-%m-%d_%H-%M-%S") + ".png"
    if not os.path.exists(dir):
        os.makedirs(dir)
    plt.savefig(fig_name)
    plt.show()
    plt.close()
    data_saver.add_item("x_axis", x_axis)
    data_saver.add_item("y_axis", y_axis)
    data_saver.to_file()


if __name__ == "__main__":
    # region_error()
    cdf_mse()
    # sum_data_influence()
    # sum_data_influence_uniform()
    # uniform_fim()
    # topo = Topology(var_vector=[4,5,6,1,2],way="Direct")
    # region_error_direct()
    # sum_data_influence_direct()
    # uniform_direct()
    # topo = Topology(var_vector=[5,6,15,20,10])
    # print(topo.reduced_matrix)
    # print(topo.Phi)
    # print(topo.proportion)
    pass
