# @Time   : 2020/6/28
# @Author : Zihan Lin
# @Email  : linzihan.super@foxmail.com

# UPDATE
# @Time   : 2020/10/04
# @Author : Shanlei Mu
# @Email  : slmu@ruc.edu.cn

import os
import sys
import yaml
import torch
from logging import getLogger

from recbox.evaluator import loss_metrics, topk_metrics
from recbox.utils import get_model, Enum, EvaluatorType


class Config(object):
    def __init__(self, model, dataset, config_file_list=None, config_dict=None):

        self.model, self.dataset = model, dataset
        self._init_parameters_category()
        self._load_init_config_dict(model, dataset)
        self._load_config_files(config_file_list)
        self.variable_config_dict = config_dict if config_dict else dict()
        self._read_cmd_line()

        self.final_config_dict = self._merge_config_dict()
        self._set_default_parameters()
        self._init_device()

    def _load_init_config_dict(self, model, dataset):
        data_path = os.path.dirname(os.path.realpath(__file__))
        overall_init_file = os.path.join(data_path, '../properties/overall.yaml')
        model_init_file = os.path.join(data_path, '../properties/model/' + model + '.yaml')
        dataset_init_file = os.path.join(data_path, '../properties/dataset/' + dataset + '.yaml')

        self.init_config_dict = dict()
        for file in [overall_init_file, model_init_file, dataset_init_file]:
            if os.path.isfile(file):
                with open(file, 'r', encoding='utf-8') as f:
                    config_dict = yaml.load(f.read(), Loader=yaml.FullLoader)
                    if file == dataset_init_file:
                        self.parameters['Dataset'] += [key for key in config_dict.keys() if
                                                       key not in self.parameters['Dataset']]
                    self.init_config_dict.update(config_dict)

    def _load_config_files(self, file_list):
        self.file_config_dict = dict()
        if file_list:
            for file in file_list:
                if os.path.isfile(file):
                    with open(file, 'r', encoding='utf-8') as f:
                        self.file_config_dict.update(yaml.load(f.read(), Loader=yaml.FullLoader))

    def convert_cmd_args(self):
        r"""This function convert the str parameters to their original type.

        """
        for key in self.cmd_config_dict:
            param = self.cmd_config_dict[key]
            if not isinstance(param, str):
                continue
            try:
                value = eval(param)
                if not isinstance(value, (str, int, float, list, tuple, dict, bool, Enum)):
                    value = param
            except (NameError, SyntaxError, TypeError):
                if isinstance(param, str):
                    if param.lower() == "true":
                        value = True
                    elif param.lower() == "false":
                        value = False
                    else:
                        value = param
                else:
                    value = param
            self.cmd_config_dict[key] = value

    def _read_cmd_line(self):
        r""" Read parameters from command line and convert it to str.

        """
        self.cmd_config_dict = dict()
        unrecognized_args = []
        if "ipykernel_launcher" not in sys.argv[0]:
            for arg in sys.argv[1:]:
                if not arg.startswith("--") or len(arg[2:].split("=")) != 2:
                    unrecognized_args.append(arg)
                    continue
                cmd_arg_name, cmd_arg_value = arg[2:].split("=")
                if cmd_arg_name in self.cmd_config_dict and cmd_arg_value != self.cmd_config_dict[cmd_arg_name]:
                    raise SyntaxError("There are duplicate commend arg '%s' with different value!" % arg)
                else:
                    self.cmd_config_dict[cmd_arg_name] = cmd_arg_value
        if len(unrecognized_args) > 0:
            logger = getLogger()
            logger.warning('command line args [{}] will not be used in RecBox'.format(' '.join(unrecognized_args)))

        self.convert_cmd_args()

    def _merge_config_dict(self):
        final_config_dict = dict()
        final_config_dict.update(self.init_config_dict)
        final_config_dict.update(self.file_config_dict)
        final_config_dict.update(self.variable_config_dict)
        final_config_dict.update(self.cmd_config_dict)
        return final_config_dict

    def _set_default_parameters(self):

        self.final_config_dict['dataset'] = self.dataset
        self.final_config_dict['model'] = self.model
        self.final_config_dict['data_path'] = os.path.join(self.final_config_dict['data_path'], self.dataset)

        eval_type = None
        for metric in self.final_config_dict['metrics']:
            if metric.lower() in loss_metrics:
                if eval_type is not None and eval_type == EvaluatorType.RANKING:
                    raise RuntimeError('Ranking metrics and other metrics can not be used at the same time!')
                else:
                    eval_type = EvaluatorType.INDIVIDUAL
            if metric.lower() in topk_metrics:
                if eval_type is not None and eval_type == EvaluatorType.INDIVIDUAL:
                    raise RuntimeError('Ranking metrics and other metrics can not be used at the same time!')
                else:
                    eval_type = EvaluatorType.RANKING
        self.final_config_dict['eval_type'] = eval_type

        smaller_metric = ['rmse', 'mae', 'logloss']
        valid_metric = self.final_config_dict['valid_metric'].split('@')[0]
        self.final_config_dict['valid_metric_bigger'] = False if valid_metric in smaller_metric else True

        model = get_model(self.model)
        self.final_config_dict['MODEL_TYPE'] = model.type
        self.final_config_dict['MODEL_INPUT_TYPE'] = model.input_type

    def _init_device(self):
        use_gpu = self.final_config_dict['use_gpu']
        if use_gpu:
            os.environ["CUDA_VISIBLE_DEVICES"] = str(self.final_config_dict['gpu_id'])
        self.final_config_dict['device'] = torch.device("cuda" if torch.cuda.is_available() and use_gpu else "cpu")

    def _init_parameters_category(self):
        self.parameters = dict()
        self.parameters['General'] = ['gpu_id', 'use_gpu', 'seed', 'data_path']
        self.parameters['Training'] = ['epochs', 'train_batch_size', 'learner', 'learning_rate',
                                       'training_neg_sample_num', 'eval_step', 'valid_metric',
                                       'stopping_step', 'checkpoint_dir']
        self.parameters['Evaluation'] = ['eval_setting', 'group_by_user', 'split_ratio', 'leave_one_num',
                                         'real_time_process', 'metrics', 'topk', 'eval_batch_size']
        self.parameters['Dataset'] = []

    def __setitem__(self, key, value):
        if not isinstance(key, str):
            raise TypeError("index must be a str")
        self.final_config_dict[key] = value

    def __getitem__(self, item):
        if item in self.final_config_dict:
            return self.final_config_dict[item]
        else:
            return None

    def __contains__(self, key):
        if not isinstance(key, str):
            raise TypeError("index must be a str!")
        return key in self.final_config_dict

    def __str__(self):
        args_info = ''
        for category in self.parameters:
            args_info += category + ' Hyper Parameters: \n'
            args_info += '\n'.join(
                ["{}={}".format(arg, value) for arg, value in self.final_config_dict.items() if arg in self.parameters[category]])
            args_info += '\n\n'
        return args_info

    def __repr__(self):
        return self.__str__()
