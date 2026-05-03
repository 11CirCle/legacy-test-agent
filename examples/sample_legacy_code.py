"""
示例遗留代码 —— 模拟一个复杂的订单处理模块，包含多分支、异常处理和边界条件。

此文件用于演示 legacy-test-agent 的测试生成能力。
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class OrderStatus(Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


@dataclass
class OrderItem:
    product_id: str
    quantity: int
    unit_price: float


@dataclass
class Order:
    order_id: str
    customer_id: str
    items: list[OrderItem]
    status: OrderStatus = OrderStatus.PENDING
    discount_code: Optional[str] = None
    shipping_address: Optional[str] = None


DISCOUNT_CODES = {
    "SAVE10": 0.10,
    "SAVE20": 0.20,
    "VIP50": 0.50,
}


def calculate_order_total(order: Order) -> float:
    if not order.items:
        raise ValueError("订单必须包含至少一个商品")

    subtotal = 0.0
    for item in order.items:
        if item.quantity <= 0:
            raise ValueError(f"商品 {item.product_id} 数量必须大于 0")
        if item.unit_price < 0:
            raise ValueError(f"商品 {item.product_id} 单价不能为负数")
        subtotal += item.quantity * item.unit_price

    discount = 0.0
    if order.discount_code:
        discount_rate = DISCOUNT_CODES.get(order.discount_code.upper())
        if discount_rate:
            discount = subtotal * discount_rate

    total = subtotal - discount

    if total < 0:
        total = 0.0

    return round(total, 2)


def can_cancel_order(order: Order) -> bool:
    if order.status == OrderStatus.CANCELLED:
        return False

    if order.status == OrderStatus.DELIVERED:
        return False

    if order.status == OrderStatus.SHIPPED:
        return False

    return True


def apply_bulk_discount(items: list[OrderItem], threshold: int = 5) -> float:
    if not items:
        return 0.0

    total_quantity = sum(item.quantity for item in items)

    if total_quantity >= threshold:
        return 0.15
    elif total_quantity >= 3:
        return 0.05
    else:
        return 0.0


def merge_orders(order1: Order, order2: Order) -> Order:
    if order1.customer_id != order2.customer_id:
        raise ValueError("不能合并不同客户的订单")

    if order1.status == OrderStatus.CANCELLED or order2.status == OrderStatus.CANCELLED:
        raise ValueError("不能合并已取消的订单")

    merged_items = order1.items + order2.items
    merged_status = (
        order1.status
        if order1.status.value < order2.status.value
        else order2.status
    )

    return Order(
        order_id=f"{order1.order_id}_{order2.order_id}",
        customer_id=order1.customer_id,
        items=merged_items,
        status=merged_status,
        discount_code=order1.discount_code or order2.discount_code,
        shipping_address=order1.shipping_address or order2.shipping_address,
    )


def get_order_summary(order: Order) -> dict:
    total = calculate_order_total(order)
    item_count = sum(item.quantity for item in order.items)

    summary = {
        "order_id": order.order_id,
        "status": order.status.value,
        "item_count": item_count,
        "total": total,
    }

    if order.discount_code:
        summary["discount_applied"] = order.discount_code

    if item_count > 10:
        summary["large_order"] = True

    return summary
