"""Build the order workbook on demand from the authoritative database.

The workbook template is packaged with the application.  Reports are returned
as bytes and are never saved to the application filesystem, which is ephemeral
on Render.
"""
from copy import copy
from io import BytesIO
from pathlib import Path

from django.conf import settings
from openpyxl import load_workbook


WORKBOOK_PATH = Path(settings.BASE_DIR) / "order_reports" / "Bharat_Mart_Orders_Template.xlsx"
ORDER_HEADERS = ["Order ID", "Order Date", "Order Time", "Customer Name", "Customer Email", "Mobile Number", "Full Delivery Address", "City", "State", "PIN Code", "Order Amount", "Coupon Code", "Coupon Discount", "Payment Method", "Payment Status", "Order Status"]
ITEM_HEADERS = ["Order ID", "Product Name", "Product Category", "Quantity", "Unit Price", "Product Discount", "Final Item Amount"]


def _order_row(order):
    customer = order.customer
    address = order.delivery_address_text or f"{customer.street}, {customer.address}"
    return [order.pk, order.created_at.date(), order.created_at.time().replace(tzinfo=None), customer.full_name, customer.user.email, customer.mobile, address, order.delivery_city or customer.city, order.delivery_state, order.delivery_pin_code or customer.postcode, float(order.total_amount), order.coupon.code if order.coupon else "", float(order.coupon_discount), order.get_payment_method_display(), order.payment_status, order.get_status_display()]


def _item_row(order, item):
    return [order.pk, item.product.name, item.product.category, item.quantity, float(item.price), 0, float(item.subtotal)]


def _validate_sheet(sheet, headers):
    if [cell.value for cell in sheet[1]][:len(headers)] != headers:
        raise ValueError("Workbook worksheet names or column headers do not match the supplied template.")


def _prepare_rows(sheet, column_count, rows):
    """Clear only cell values, retaining all template styles and dimensions."""
    for row_number in range(2, sheet.max_row + 1):
        for column in range(1, column_count + 1):
            sheet.cell(row_number, column).value = None
    for row_number, values in enumerate(rows, start=2):
        # The supplied template has many formatted blank rows.  Should a report
        # outgrow them, copy row-two formatting instead of creating plain rows.
        if row_number > sheet.max_row:
            for column in range(1, column_count + 1):
                sheet.cell(row_number, column)._style = copy(sheet.cell(2, column)._style)
                sheet.cell(row_number, column).number_format = sheet.cell(2, column).number_format
        for column, value in enumerate(values, start=1):
            sheet.cell(row_number, column).value = value
    last_row = max(1, 1 + len(rows))
    last_column = sheet.cell(1, column_count).coordinate.rstrip("1")
    sheet.auto_filter.ref = f"A1:{last_column}{last_row}"


def generate_order_report():
    """Return a freshly generated XLSX report containing every DB order once."""
    if not WORKBOOK_PATH.is_file():
        raise FileNotFoundError("Required order report template is missing.")
    from .models import Order

    # `prefetch_related` guarantees every item is included without per-item
    # queries; database records, not any prior workbook, prevent duplicates.
    orders = list(
        Order.objects.select_related("customer__user", "coupon")
        .prefetch_related("items__product")
        .order_by("id")
    )
    workbook = load_workbook(WORKBOOK_PATH)
    orders_sheet = workbook["Orders"]
    items_sheet = workbook["Order Items"]
    _validate_sheet(orders_sheet, ORDER_HEADERS)
    _validate_sheet(items_sheet, ITEM_HEADERS)
    _prepare_rows(orders_sheet, len(ORDER_HEADERS), [_order_row(order) for order in orders])
    _prepare_rows(
        items_sheet,
        len(ITEM_HEADERS),
        [_item_row(order, item) for order in orders for item in order.items.all()],
    )
    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return output


def export_order_after_commit(order_id):
    """Compatibility hook for checkout; reports are now generated on download."""
    # Deliberately does not write a generated workbook to Render's filesystem.
    return None


def export_order(order):
    """Backward-compatible hook; a report is generated from all orders on download."""
    return None


def reconcile_workbook():
    """Backward-compatible validation/generation helper with no persistent write."""
    return generate_order_report()


regenerate_workbook = reconcile_workbook
