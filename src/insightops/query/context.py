"""Build bounded, oracle-free Text2SQL context from public project metadata."""

import json
from dataclasses import dataclass

from sqlalchemy import MetaData

from insightops.benchmark.contracts import PublicBenchmarkCase
from insightops.db.models import Base
from insightops.seed.contracts import DatasetManifest

_METRIC_DEFINITIONS = {
    "MRR": "指定时点有效订阅的规范化月度周期性费用；年付金额除以 12。",
    "ARR": "同一快照时点的 MRR 乘以 12，不是实际支付收入。",
    "SaaS Revenue": "按支付成功时间统计的订阅费用实际收款，不含税费和一次性费用。",
    "Churned MRR": "取消生效前订阅的全部规范化 MRR 损失，以正数表达。",
    "GMV": "按订单首次支付成功时间统计折扣后商品金额，不扣退款。",
    "Order Count": "报表期内合格支付订单去重计数。",
    "AOV": "GMV 除以 Order Count；分母为零时返回 null。",
    "SaaS CAC": "同期实际广告花费除以新增 SaaS 付费 organization 数。",
    "Attributed Revenue": "必须明确为 SaaS 或 Commerce 的权威收入，并按转化时间归属。",
    "Attributed ROAS": "明确收入类型的归因收入除以同期实际广告花费；零分母为 null。",
}

_GLOBAL_RULES = (
    "数据库会话使用 UTC；业务日期使用数据集声明的业务时区。",
    "所有事实必须满足 snapshot cutoff，并显式排除 is_test = 1 的记录及其归属链。",
    "快照指标不得跨时点相加；SaaS Revenue、MRR、GMV 与平台收入不可互换。",
    "只生成一条 MySQL SELECT/CTE 查询，禁止通配符投影和带库名的表引用。",
    "只可使用给定命名参数；不要内联上下文已提供的参数值。",
)


@dataclass(frozen=True)
class QueryContext:
    """Provider-ready prompt material and public routing metadata."""

    system_prompt: str
    user_prompt: str
    case: PublicBenchmarkCase | None


def build_query_context(
    *,
    question: str,
    case: PublicBenchmarkCase | None,
    manifest: DatasetManifest,
    clarification_code: str | None = None,
) -> QueryContext:
    """Create a finite context without consulting benchmark-only assets."""
    relevant_tables = case.required_tables if case is not None else manifest.table_order
    schema = _public_schema(Base.metadata, relevant_tables)
    metrics = case.metrics if case is not None else tuple(_METRIC_DEFINITIONS)
    definitions = [
        {"metric": metric, "definition": _METRIC_DEFINITIONS[metric]}
        for metric in metrics
        if metric in _METRIC_DEFINITIONS
    ]
    case_payload: dict[str, object] | None = None
    if case is not None:
        case_payload = case.model_dump(mode="json")
        if clarification_code is not None:
            case_payload["accepted_clarification_code"] = clarification_code

    payload = {
        "question": question,
        "dataset": {
            "business_timezone": manifest.business_timezone,
            "snapshot_cutoff_utc": manifest.snapshot_cutoff.isoformat(),
        },
        "business_rules": _GLOBAL_RULES,
        "metric_definitions": definitions,
        "case": case_payload,
        "schema": schema,
        "output_contract": {
            "action": ["execute_sql", "request_clarification"],
            "execute_sql_fields": ["action", "sql"],
            "request_clarification_fields": [
                "action",
                "clarification_code",
                "clarification_question",
            ],
        },
    }
    return QueryContext(
        system_prompt=(
            "You generate a safe, read-only MySQL analytics candidate from supplied public "
            "metadata. Return the structured contract exactly. Ask one concise clarification "
            "when the requested metric is ambiguous or the case requires clarification."
        ),
        user_prompt=json.dumps(payload, ensure_ascii=False, sort_keys=True),
        case=case,
    )


def _public_schema(metadata: MetaData, table_names: tuple[str, ...]) -> list[dict[str, object]]:
    schema: list[dict[str, object]] = []
    for table_name in table_names:
        table = metadata.tables[table_name]
        schema.append(
            {
                "table": table.name,
                "columns": [
                    {
                        "name": column.name,
                        "type": str(column.type),
                        "nullable": column.nullable,
                        "primary_key": column.primary_key,
                    }
                    for column in table.columns
                ],
                "foreign_keys": sorted(
                    f"{foreign_key.parent.name}->{foreign_key.target_fullname}"
                    for foreign_key in table.foreign_keys
                ),
            }
        )
    return schema
