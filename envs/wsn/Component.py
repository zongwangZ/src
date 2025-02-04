#!/usr/bin/env python
# encoding: utf-8
'''
@project : 'MEC_Q-learning'
@author  : '张宗旺'
@file    : 'Component'.py
@ide     : 'PyCharm'
@time    : '2020'-'01'-'02' '18':'30':'16'
@contact : zongwang.zhang@outlook.com
'''
from abc import ABCMeta, abstractmethod
from src.envs.wsn.Configuration import config
import numpy as np
import copy


class Component(metaclass=ABCMeta):
    cache = 0
    received = {}
    id = "c"

    @abstractmethod
    def receive_data(self, data, src_id):
        pass

    @abstractmethod
    def reset(self):
        pass


class BaseStation(Component):
    id = "b"

    def receive_data(self, data, src_id):
        self.cache += data
        if src_id not in self.received:
            self.received[src_id] = data
        else:
            self.received[src_id] += data

    def reset(self):
        self.cache = 0
        self.received = {}


class Satellite(Component):
    id = "s"

    def receive_data(self, data, src_id):
        self.cache += data
        if src_id not in self.received:
            self.received[src_id] = data
        else:
            self.received[src_id] += data

    def reset(self):
        self.cache = 0
        self.received = {}


class Sensor(Component):

    def __init__(self, id):
        self.id = id
        self.connection = config.get("connections")[id]
        self.sampled_data = 0
        self.received_data = 0
        self.received = {}
        self.receiving = {}
        self.MAX_CACHE_SIZE = config.get("MAX_CACHE_SIZE")[self.id]
        self.state = np.zeros(config.get("observation_size"))
        self.sample_rate = config.get("sample_rate")
        self.decision_interval = config.get("decision_interval")

    def send_data(self, receiver, data, src_id):
        assert isinstance(receiver, Component)
        loss_rate = self.get_loss_rate(receiver.id)
        self.transmit_data(receiver, data, loss_rate, src_id)

    def transmit_data(self, receiver, data, loss_rate, src_id):
        if np.random.uniform(0, 1) > loss_rate:
            receiver.receive_data(data, src_id)
        else:
            receiver.receive_data(0, src_id)
        # receiver.receive_data(data*(1-loss_rate), src_id)

    def receive_data(self, data, src_id):
        if src_id not in self.receiving:
            self.receiving[src_id] = data
        else:
            self.receiving[src_id] += data

    def do_action(self, action, components):
        '''
        将action对应的数据发送出去，将上回合收到的转发数据转发出去
        :param action:
        :param components:
        :return:
        '''
        # 将本回合采集的数据发送出去
        corresponding_id = action
        component_id = self.connection[corresponding_id]
        for component in components:
            assert isinstance(component, Component)
            if component_id == component.id:
                data = self.sampled_data
                self.send_data(component, data, component.id)
                self.sampled_data -= data
                assert self.sampled_data == 0
                self.cache -= data

        next_hop = 0
        next_hop_id = self.connection[1]
        for component in components:
            if component.id == next_hop_id:
                next_hop = component
        assert isinstance(next_hop, Component)
        for src_id in self.received:
            data = self.received[src_id]
            self.send_data(next_hop, data, src_id)
            self.received_data -= data
            self.received[src_id] -= data
            self.cache -= data


    def do_settlement(self):
        '''
        接收别人转发的数据
        :return:
        '''
        for src_id in self.receiving:
            data = self.receiving[src_id]
            if self.cache + data > self.MAX_CACHE_SIZE:
                available_data = self.cache + data - self.MAX_CACHE_SIZE
            else:
                available_data = data
            if src_id not in self.received:
                self.received[src_id] = available_data
            else:
                self.received[src_id] += available_data
            self.receiving[src_id] = 0
            self.received_data += available_data
            self.cache += available_data

    def reset(self):
        self.cache = 0
        self.received_data = 0
        self.received = {}
        self.receiving = {}
        self.sampled_data = 0
        ##重置状态
        self.reset_state()

    def reset_state(self):
        self.state = np.zeros(config.get("observation_size"))

    def get_observation(self, components):
        '''
        包括状态：目前只有loss rate
        :param components:
        :return:
        '''
        self.set_cache()
        # loss rate
        loss_rate = np.array([
            self.get_loss_rate(self.connection[0]),
            self.get_loss_rate(self.connection[1]),
            self.get_loss_rate(self.connection[2])
        ])
        # cache

        self.state = loss_rate
        assert isinstance(self.state, np.ndarray)
        return copy.deepcopy(self.state)

    def sample_data(self):
        sampling_data = self.decision_interval*self.sample_rate
        if self.cache + sampling_data > self.MAX_CACHE_SIZE:
            available_data = self.cache + sampling_data - self.MAX_CACHE_SIZE
        else:
            available_data = sampling_data
        self.sampled_data += available_data
        self.set_cache()

    def get_loss_rate(self, c):
        assert isinstance(self.connection, list)
        index = self.connection.index(c)
        loss_rate = config.get("loss_rate")[self.id][index]
        return loss_rate

    def set_cache(self):
        self.cache = self.sampled_data + self.received_data
        assert self.cache <= self.MAX_CACHE_SIZE
