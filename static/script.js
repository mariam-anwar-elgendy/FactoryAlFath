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

// ========== تحديث عدّاد الشات (كل 10 ثواني) ==========
document.addEventListener('DOMContentLoaded', function() {
    const navbarBadge = document.querySelector('.navbar-badge');
    const sidebarBadge = document.querySelector('.sidebar-chat-badge');
    
    // لو مفيش badges، مش محتاجين نعمل حاجة
    if (!navbarBadge && !sidebarBadge) return;

    function updateChatBadge() {
        fetch('/chat/unread-count')
            .then(response => response.json())
            .then(data => {
                if (navbarBadge) {
                    if (data.total > 0) {
                        navbarBadge.innerText = data.total;
                        navbarBadge.style.display = 'inline-block';
                    } else {
                        navbarBadge.style.display = 'none';
                    }
                }
                if (sidebarBadge) {
                    if (data.total > 0) {
                        sidebarBadge.innerText = data.total;
                        sidebarBadge.style.display = 'inline-block';
                    } else {
                        sidebarBadge.style.display = 'none';
                    }
                }
            })
            .catch(error => {
                // نتجاهل الأخطاء (مثلاً لو المستخدم مش مسجل دخول)
            });
    }

    updateChatBadge();
    setInterval(updateChatBadge, 10000);
});

// ========== تحسينات الموبايل للنماذج ==========
document.addEventListener('DOMContentLoaded', function() {
    // تصغير الخط في الحقول على الموبايل تلقائياً
    if (window.innerWidth <= 768) {
        document.querySelectorAll('input, select, textarea').forEach(function(input) {
            // منع الـ zoom التلقائي على iOS
            if (input.type !== 'checkbox' && input.type !== 'radio' && input.type !== 'file') {
                if (!input.style.fontSize) {
                    input.style.fontSize = '16px';
                }
            }
        });
    }
});

// ========== منع الـ zoom التلقائي على iOS ==========
document.addEventListener('DOMContentLoaded', function() {
    // منع pinch zoom على iOS
    document.addEventListener('gesturestart', function(e) {
        e.preventDefault();
    });
    
    // منع double-tap zoom
    let lastTouchEnd = 0;
    document.addEventListener('touchend', function(e) {
        const now = (new Date()).getTime();
        if (now - lastTouchEnd <= 300) {
            e.preventDefault();
        }
        lastTouchEnd = now;
    }, false);
});
