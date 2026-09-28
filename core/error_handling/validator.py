"""
工具参数验证器 - 在工具选择和执行前进行验证

Author: EduClaw Team
Date: 2026-09-28
"""

from typing import Any, Dict, List, Callable, Optional
from logging import getLogger
import inspect

from .exceptions import ToolParameterError, ToolValidationError

logger = getLogger("VALIDATOR")


class ParameterValidator:
    """
    参数验证器

    功能：
    - 验证工具参数类型
    - 验证参数范围和约束
    - 自定义验证规则
    - 生成详细的验证错误报告
    """

    def __init__(self):
        """初始化验证器"""
        self.custom_validators: Dict[str, List[Callable]] = {}

    def register_validator(self, tool_name: str, validator_func: Callable):
        """
        注册自定义验证器

        Args:
            tool_name: 工具名称
            validator_func: 验证函数，接收参数字典，返回 (is_valid, errors_list)
        """
        if tool_name not in self.custom_validators:
            self.custom_validators[tool_name] = []
        self.custom_validators[tool_name].append(validator_func)
        logger.info(f"Registered validator for {tool_name}")

    def validate_parameters(self, tool_name: str, parameters: Dict[str, Any],
                            schema: Dict = None) -> tuple[bool, List[str]]:
        """
        验证工具参数

        Args:
            tool_name: 工具名称
            parameters: 参数字典
            schema: JSON Schema 对象（可选）

        Returns:
            (is_valid, error_list)
        """
        errors = []

        # 基础检查
        if not isinstance(parameters, dict):
            errors.append(f"参数必须是字典类型，实际为 {type(parameters).__name__}")
            return False, errors

        # 使用 schema 进行验证
        if schema:
            schema_errors = self._validate_against_schema(parameters, schema)
            errors.extend(schema_errors)

        # 运行自定义验证器
        if tool_name in self.custom_validators:
            for validator in self.custom_validators[tool_name]:
                try:
                    is_valid, validator_errors = validator(parameters)
                    if not is_valid:
                        errors.extend(validator_errors)
                except Exception as e:
                    errors.append(f"Custom validator error: {str(e)}")

        is_valid = len(errors) == 0
        if not is_valid:
            logger.warning(f"Validation failed for {tool_name}: {errors}")

        return is_valid, errors

    def _validate_against_schema(self, data: Dict, schema: Dict) -> List[str]:
        """根据 JSON Schema 验证数据"""
        errors = []

        # 验证必需字段
        required_fields = schema.get("required", [])
        for field in required_fields:
            if field not in data:
                errors.append(f"缺少必需参数: '{field}'")

        # 验证属性
        properties = schema.get("properties", {})
        for field_name, field_value in data.items():
            if field_name in properties:
                field_schema = properties[field_name]
                field_errors = self._validate_field(field_name, field_value, field_schema)
                errors.extend(field_errors)
            else:
                # 检查是否允许额外属性
                if not schema.get("additionalProperties", True):
                    errors.append(f"不允许的参数: '{field_name}'")

        return errors

    def _validate_field(self, field_name: str, value: Any, schema: Dict) -> List[str]:
        """验证单个字段"""
        errors = []

        # 类型检查
        expected_type = schema.get("type")
        if expected_type:
            if not self._type_matches(value, expected_type):
                actual_type = self._get_python_type_name(value)
                errors.append(
                    f"参数 '{field_name}' 类型错误: 期望 {expected_type}，实际 {actual_type}"
                )
                return errors  # 如果类型错误，跳过后续检查

        # 字符串长度检查
        if isinstance(value, str):
            if "minLength" in schema and len(value) < schema["minLength"]:
                errors.append(
                    f"参数 '{field_name}' 长度过短: 最小长度 {schema['minLength']}, "
                    f"实际长度 {len(value)}"
                )
            if "maxLength" in schema and len(value) > schema["maxLength"]:
                errors.append(
                    f"参数 '{field_name}' 长度过长: 最大长度 {schema['maxLength']}, "
                    f"实际长度 {len(value)}"
                )

            # 正则表达式检查
            if "pattern" in schema:
                import re
                if not re.match(schema["pattern"], value):
                    errors.append(
                        f"参数 '{field_name}' 不匹配模式: {schema['pattern']}"
                    )

        # 数值范围检查
        if isinstance(value, (int, float)):
            if "minimum" in schema and value < schema["minimum"]:
                errors.append(
                    f"参数 '{field_name}' 过小: 最小值 {schema['minimum']}, 实际值 {value}"
                )
            if "maximum" in schema and value > schema["maximum"]:
                errors.append(
                    f"参数 '{field_name}' 过大: 最大值 {schema['maximum']}, 实际值 {value}"
                )

        # 枚举值检查
        if "enum" in schema:
            if value not in schema["enum"]:
                errors.append(
                    f"参数 '{field_name}' 值不被允许: 允许的值 {schema['enum']}, 实际值 {value}"
                )

        # 数组检查
        if isinstance(value, list):
            if "minItems" in schema and len(value) < schema["minItems"]:
                errors.append(
                    f"参数 '{field_name}' 数组元素过少: 最小数量 {schema['minItems']}"
                )
            if "maxItems" in schema and len(value) > schema["maxItems"]:
                errors.append(
                    f"参数 '{field_name}' 数组元素过多: 最大数量 {schema['maxItems']}"
                )

        return errors

    @staticmethod
    def _type_matches(value: Any, expected_type: str) -> bool:
        """检查值是否匹配期望的类型"""
        type_map = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
            "null": type(None),
        }

        if expected_type not in type_map:
            return True

        expected_python_type = type_map[expected_type]
        return isinstance(value, expected_python_type)

    @staticmethod
    def _get_python_type_name(value: Any) -> str:
        """获取 Python 类型的 JSON Schema 类型名"""
        type_name = type(value).__name__

        type_map = {
            "str": "string",
            "int": "integer",
            "float": "number",
            "bool": "boolean",
            "list": "array",
            "dict": "object",
            "NoneType": "null",
        }

        return type_map.get(type_name, type_name)


def create_file_path_validator(required: bool = True,
                               allowed_extensions: List[str] = None) -> Callable:
    """创建文件路径验证器"""

    def validator(params: Dict) -> tuple[bool, List[str]]:
        errors = []
        file_path = params.get("file_path")

        if required and not file_path:
            errors.append("file_path 不能为空")
            return False, errors

        if file_path:
            import os
            if not os.path.exists(file_path):
                errors.append(f"文件不存在: {file_path}")

            if allowed_extensions:
                ext = os.path.splitext(file_path)[1].lower()
                if ext not in allowed_extensions:
                    errors.append(
                        f"文件类型不支持: {ext}，允许的类型: {allowed_extensions}"
                    )

        return len(errors) == 0, errors

    return validator


def create_timeout_validator(max_timeout: float = 300) -> Callable:
    """创建超时时间验证器"""

    def validator(params: Dict) -> tuple[bool, List[str]]:
        errors = []
        timeout = params.get("timeout")

        if timeout is not None:
            if not isinstance(timeout, (int, float)):
                errors.append(f"timeout 必须是数字类型")
            elif timeout <= 0:
                errors.append(f"timeout 必须大于 0")
            elif timeout > max_timeout:
                errors.append(
                    f"timeout 超过限制: 最大 {max_timeout}秒，实际 {timeout}秒"
                )

        return len(errors) == 0, errors

    return validator
