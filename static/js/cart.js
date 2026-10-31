function getCookie(name) {
    const cookies = document.cookie.split(";");
    for (let cookie of cookies) {
        cookie = cookie.trim();
        if (cookie.startsWith(name + "=")) return decodeURIComponent(cookie.substring(name.length + 1));
    }
    return null;
}

function cartMessage(message) {
    let notice = $("#cart-notice");
    if (!notice.length) {
        notice = $("<div id='cart-notice' class='cart-notice' role='status'></div>");
        $("body").append(notice);
    }
    notice.stop(true, true).text(message).fadeIn(150).delay(1800).fadeOut(250);
}

function hasStockLimit(value) {
    return value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value));
}

class Cart {
    constructor() {
        try {
            this.items = JSON.parse(localStorage.getItem("cart")) || [];
        } catch (error) {
            this.items = [];
        }
        this.items = this.items.filter(item => item && Number.isInteger(Number(item.product_id)) && Number(item.quantity) > 0);
    }

    save() {
        localStorage.setItem("cart", JSON.stringify(this.items));
        this.updateCount();
        $(document).trigger("cart:changed");
    }

    add(product) {
        const limited = hasStockLimit(product.stock_quantity);
        const stock = limited ? Number(product.stock_quantity) : null;
        if (limited && stock < 1) {
            cartMessage("This item is currently out of stock.");
            return false;
        }
        const item = this.items.find(item => Number(item.product_id) === Number(product.product_id));
        if (item) {
            if (limited) item.stock_quantity = stock;
            if (hasStockLimit(item.stock_quantity) && item.quantity >= Number(item.stock_quantity)) {
                cartMessage("You have reached the available quantity for this item.");
                return false;
            }
            item.quantity += 1;
        } else {
            product.quantity = 1;
            product.stock_quantity = limited ? stock : null;
            this.items.push(product);
        }
        this.save();
        return true;
    }

    remove(productId) {
        this.items = this.items.filter(item => Number(item.product_id) !== Number(productId));
        this.save();
    }

    update(productId, quantity) {
        const item = this.items.find(item => Number(item.product_id) === Number(productId));
        if (!item) return;
        quantity = Number.parseInt(quantity, 10);
        if (!Number.isFinite(quantity) || quantity <= 0) {
            this.remove(productId);
            return;
        }
        const limited = hasStockLimit(item.stock_quantity);
        const stock = limited ? Number(item.stock_quantity) : null;
        if (limited && quantity > stock) {
            quantity = stock;
            cartMessage(`Only ${stock} item${stock === 1 ? "" : "s"} currently available.`);
        }
        item.quantity = quantity;
        this.save();
    }

    total() {
        return this.items.reduce((total, item) => total + (Number.parseFloat(item.price) * item.quantity), 0);
    }

    clear() {
        this.items = [];
        localStorage.removeItem("cart");
        this.updateCount();
        $(document).trigger("cart:changed");
    }

    updateCount() {
        const count = this.items.reduce((total, item) => total + Number(item.quantity), 0);
        $("#cart-count").text(count);
    }

    checkout(options = {}) {
        if (!this.items.length) {
            cartMessage("Your bag is empty.");
            return;
        }
        const data = this.items.map(item => ({product_id: item.product_id, quantity: item.quantity}));
        $.ajax({
            url: "/orders/cart/",
            type: "POST",
            contentType: "application/json",
            headers: {"X-CSRFToken": getCookie("csrftoken")},
            data: JSON.stringify(Object.assign({items: data}, options)),
            success: (response) => {
                this.clear();
                window.location.href = response.redirect_url;
            },
            error: (response) => {
                const data = response.responseJSON || {};
                if (response.status === 401 && data.login_url) {
                    window.location.href = data.login_url;
                    return;
                }
                cartMessage(data.message || "Unable to place your order.");
            }
        });
    }
}

const cart = new Cart();
$(document).ready(function () {
    const pending = document.getElementById("pending-cart-item");
    if (pending) {
        try { cart.add(JSON.parse(pending.textContent)); } catch (error) { /* Ignore a stale session item. */ }
    }
    cart.updateCount();
});
