import json
import numpy as np


class MinelandJSONEncoder(json.JSONEncoder):
    """自定义JSON编码器，处理MineLand特有的类型"""

    def default(self, obj):
        if hasattr(obj, "__dict__"):
            return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(
            obj,
            (
                np.int_,
                np.intc,
                np.intp,
                np.int8,
                np.int16,
                np.int32,
                np.int64,
                np.uint8,
                np.uint16,
                np.uint32,
                np.uint64,
            ),
        ):
            return int(obj)
        elif isinstance(obj, (np.float_, np.float16, np.float32, np.float64)):
            return float(obj)
        elif isinstance(obj, (np.bool_)):
            return bool(obj)
        return super(MinelandJSONEncoder, self).default(obj)


def json_serialize_mineland(obj):
    """使用自定义编码器序列化MineLand对象"""
    return json.dumps(obj, cls=MinelandJSONEncoder)


def numpy_to_list_recursive(item):
    """递归地将 NumPy 数组和其他不可JSON序列化对象转换为可序列化类型。"""
    if isinstance(item, np.ndarray):
        return item.tolist()
    elif hasattr(item, "__dict__"):
        return {k: numpy_to_list_recursive(v) for k, v in item.__dict__.items() if not k.startswith("_")}
    elif isinstance(item, dict):
        return {k: numpy_to_list_recursive(v) for k, v in item.items()}
    elif isinstance(item, list) or isinstance(item, tuple):
        return [numpy_to_list_recursive(elem) for elem in item]
    elif isinstance(
        item,
        (np.int_, np.intc, np.intp, np.int8, np.int16, np.int32, np.int64, np.uint8, np.uint16, np.uint32, np.uint64),
    ):
        return int(item)
    elif isinstance(item, (np.float_, np.float16, np.float32, np.float64)):
        return float(item)
    elif isinstance(item, np.bool_):
        return bool(item)
    return item
