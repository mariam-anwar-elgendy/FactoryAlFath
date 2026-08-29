// ========== إخفاء رسائل التنبيه تلقائياً بعد 5 ثواني ==========
document.addEventListener('DOMContentLoaded', function() {
    setTimeout(function() {
        const alerts = document.querySelectorAll('.alert');
        alerts.forEach(function(alert) {
            const closeBtn = alert.querySelector('.btn-close');
            if (closeBtn) {
                closeBtn.click();
            }
        });
    }, 5000);
});

// ========== تأكيد عمليات الحذف ==========
document.addEventListener('DOMContentLoaded', function() {
    const deleteForms = document.querySelectorAll('form[onsubmit*="confirm"]');
    deleteForms.forEach(function(form) {
        form.addEventListener('submit', function(e) {
            if (!confirm('⚠️ هل أنت متأكد من الحذف؟')) {
                e.preventDefault();
            }
        });
    });
});

// ========== حساب الإجمالي تلقائياً في المبيعات والمشتريات ==========
document.addEventListener('DOMContentLoaded', function() {
    const quantityInputs = document.querySelectorAll('input[name="quantity"]');
    const priceInputs = document.querySelectorAll('input[name="unit_price"]');
    const totalInputs = document.querySelectorAll('input[disabled][placeholder="يحسب تلقائياً"]');

    function updateTotal(quantityInput, priceInput, totalInput) {
        if (quantityInput && priceInput && totalInput) {
            const qty = parseFloat(quantityInput.value) || 0;
            const price = parseFloat(priceInput.value) || 0;
            totalInput.value = (qty * price).toFixed(2);
        }
    }

    quantityInputs.forEach(function(qtyInput) {
        const form = qtyInput.closest('form');
        if (!form) return;
        const priceInput = form.querySelector('input[name="unit_price"]');
        const totalInput = form.querySelector('input[disabled][placeholder="يحسب تلقائياً"]');
        qtyInput.addEventListener('input', function() {
            updateTotal(qtyInput, priceInput, totalInput);
        });
        if (priceInput) {
            priceInput.addEventListener('input', function() {
                updateTotal(qtyInput, priceInput, totalInput);
            });
        }
    });
});

// ========== تفعيل القائمة الجانبية على التليفون ==========
document.addEventListener('DOMContentLoaded', function() {
    const sidebarToggle = document.querySelector('[data-bs-toggle="offcanvas"]');
    if (sidebarToggle) {
        sidebarToggle.addEventListener('click', function() {
            const sidebar = document.getElementById('sidebar');
            if (sidebar) {
                sidebar.classList.toggle('show');
            }
        });
    }
});
