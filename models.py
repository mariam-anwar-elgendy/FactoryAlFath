# models.py
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

# ==================== المستخدمين ====================
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    phone = db.Column(db.String(20))
    is_hidden = db.Column(db.Boolean, default=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_activity = db.Column(db.DateTime)
    notifications = db.relationship('Notification', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# ==================== التصنيفات والمقاسات ====================
class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

class Size(db.Model):
    __tablename__ = 'sizes'
    id = db.Column(db.Integer, primary_key=True)
    value = db.Column(db.String(50), unique=True, nullable=False)

class Thickness(db.Model):
    __tablename__ = 'thicknesses'
    id = db.Column(db.Integer, primary_key=True)
    value = db.Column(db.String(50), unique=True, nullable=False)

# ==================== العملاء والموردين ====================
class Customer(db.Model):
    __tablename__ = 'customers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    phone = db.Column(db.String(20))

class Supplier(db.Model):
    __tablename__ = 'suppliers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    phone = db.Column(db.String(20))

# ==================== المصنع ====================
class FactoryRawMaterial(db.Model):
    __tablename__ = 'factory_raw_materials'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    pipe_size = db.Column(db.String(50))
    pipe_thickness = db.Column(db.String(50))
    quantity = db.Column(db.Float, nullable=False)
    supplier = db.Column(db.String(100))
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class FactoryProduction(db.Model):
    __tablename__ = 'factory_production'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    elbow_size = db.Column(db.String(50))
    elbow_thickness = db.Column(db.String(50))
    quantity = db.Column(db.Float, nullable=False)
    raw_material_used = db.Column(db.Float, default=0)
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class FactoryDiary(db.Model):
    __tablename__ = 'factory_diary'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    description = db.Column(db.Text, nullable=False)
    amount = db.Column(db.Float, default=0)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ==================== المحل ====================
class StoreSale(db.Model):
    __tablename__ = 'store_sales'
    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(50), unique=True, nullable=False)
    customer_name = db.Column(db.String(100), nullable=False)
    customer_phone = db.Column(db.String(20))
    payment_type = db.Column(db.String(20), default='آجل')
    date = db.Column(db.Date, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship('StoreSaleItem', backref='sale', lazy=True, cascade='all, delete-orphan')
    payments = db.relationship('Payment', backref='sale', lazy=True, cascade='all, delete-orphan')

    @property
    def total(self):
        return sum(item.total for item in self.items)

    @property
    def paid_amount(self):
        return sum(p.amount for p in self.payments)

    @property
    def remaining(self):
        return self.total - self.paid_amount

class StorePurchase(db.Model):
    __tablename__ = 'store_purchases'
    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(50), unique=True, nullable=False)
    supplier_name = db.Column(db.String(100), nullable=False)
    supplier_phone = db.Column(db.String(20))
    payment_type = db.Column(db.String(20), default='آجل')
    date = db.Column(db.Date, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship('StorePurchaseItem', backref='purchase', lazy=True, cascade='all, delete-orphan')
    payments = db.relationship('Payment', backref='purchase', lazy=True, cascade='all, delete-orphan')

    @property
    def total(self):
        return sum(item.total for item in self.items)

    @property
    def paid_amount(self):
        return sum(p.amount for p in self.payments)

    @property
    def remaining(self):
        return self.total - self.paid_amount

class StoreSaleItem(db.Model):
    __tablename__ = 'store_sale_items'
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('store_sales.id'), nullable=False)
    product_type = db.Column(db.String(100))
    product_size = db.Column(db.String(50))
    product_spec = db.Column(db.String(50))
    quantity = db.Column(db.Float, nullable=False)
    unit_price = db.Column(db.Float, default=0)
    total = db.Column(db.Float, default=0)

class StorePurchaseItem(db.Model):
    __tablename__ = 'store_purchase_items'
    id = db.Column(db.Integer, primary_key=True)
    purchase_id = db.Column(db.Integer, db.ForeignKey('store_purchases.id'), nullable=False)
    product_type = db.Column(db.String(100))
    product_size = db.Column(db.String(50))
    product_spec = db.Column(db.String(50))
    quantity = db.Column(db.Float, nullable=False)
    unit_price = db.Column(db.Float, default=0)
    total = db.Column(db.Float, default=0)

class StoreInventory(db.Model):
    __tablename__ = 'store_inventory'
    id = db.Column(db.Integer, primary_key=True)
    product_type = db.Column(db.String(100), nullable=False)
    product_size = db.Column(db.String(50))
    product_spec = db.Column(db.String(50))
    current_quantity = db.Column(db.Float, default=0)
    min_quantity = db.Column(db.Float, default=0)

class StoreReceiving(db.Model):
    __tablename__ = 'store_receiving'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    product_type = db.Column(db.String(100))
    product_size = db.Column(db.String(50))
    product_spec = db.Column(db.String(50))
    quantity = db.Column(db.Float, nullable=False)
    supplier = db.Column(db.String(100))
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class StoreReturn(db.Model):
    __tablename__ = 'store_returns'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    return_type = db.Column(db.String(20))
    party_name = db.Column(db.String(100))
    product_type = db.Column(db.String(100))
    product_size = db.Column(db.String(50))
    product_spec = db.Column(db.String(50))
    quantity = db.Column(db.Float, nullable=False)
    reason = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class StoreDiary(db.Model):
    __tablename__ = 'store_diary'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    description = db.Column(db.Text, nullable=False)
    amount = db.Column(db.Float, default=0)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Payment(db.Model):
    __tablename__ = 'payments'
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('store_sales.id'))
    purchase_id = db.Column(db.Integer, db.ForeignKey('store_purchases.id'))
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.Date, nullable=False)
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ==================== الخزينة ====================
class TreasuryAccount(db.Model):
    __tablename__ = 'treasury_accounts'
    id = db.Column(db.Integer, primary_key=True)
    person_name = db.Column(db.String(100), nullable=False)
    account_type = db.Column(db.String(50), nullable=False)
    balance = db.Column(db.Float, default=0)
    transactions = db.relationship('TreasuryTransaction', backref='account', lazy=True, cascade='all, delete-orphan')

class TreasuryTransaction(db.Model):
    __tablename__ = 'treasury_transactions'
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('treasury_accounts.id'), nullable=False)
    transaction_type = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    source = db.Column(db.String(200))
    payment_method = db.Column(db.String(50))
    date = db.Column(db.Date, nullable=False)
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class TreasuryTransfer(db.Model):
    __tablename__ = 'treasury_transfers'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    from_person = db.Column(db.String(100), nullable=False)
    to_person = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(50))
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ==================== السجلات ====================
class EditLog(db.Model):
    __tablename__ = 'edit_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    table_name = db.Column(db.String(50))
    record_id = db.Column(db.Integer)
    action = db.Column(db.String(20))
    old_value = db.Column(db.Text)
    new_value = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ActivityLog(db.Model):
    __tablename__ = 'activity_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(50), nullable=False)
    details = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


# ====================================================================
# ==================== شركة الماسة - الأنواع الثلاثة ====================
# ====================================================================

# --------------------------------------------------------------------
# النوع 1: ونش مشاركة براس المال
# --------------------------------------------------------------------
class AlMasaCrane(db.Model):
    """ونش مشاركة براس المال"""
    __tablename__ = 'almasa_cranes'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    notes = db.Column(db.Text)
    crane_type = db.Column(db.String(20), default='partnership')  # partnership / private
    owner_name = db.Column(db.String(100))  # اسم صاحب الونش لو خاص
    partners = db.relationship('AlMasaPartner', backref='crane', lazy=True, cascade="all, delete-orphan")
    operations = db.relationship('AlMasaOperation', backref='crane', lazy=True, cascade="all, delete-orphan")
    checks = db.relationship('AlMasaCheck', backref='crane', lazy=True, cascade="all, delete-orphan")
    expenses = db.relationship('AlMasaExpense', backref='crane', lazy=True, cascade="all, delete-orphan")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AlMasaPartner(db.Model):
    """شركاء ونش المشاركة"""
    __tablename__ = 'almasa_partners'
    id = db.Column(db.Integer, primary_key=True)
    crane_id = db.Column(db.Integer, db.ForeignKey('almasa_cranes.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    percentage = db.Column(db.Float, default=0)
    is_basic = db.Column(db.Boolean, default=False)  # شريك أساسي (الفتح/أحمد)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AlMasaOperation(db.Model):
    """عمليات ونش المشاركة"""
    __tablename__ = 'almasa_operations'
    id = db.Column(db.Integer, primary_key=True)
    crane_id = db.Column(db.Integer, db.ForeignKey('almasa_cranes.id'), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date)
    actual_daily_value = db.Column(db.Float, default=0)  # القيمة الفعلية لليوم
    default_daily_value = db.Column(db.Float, default=0)  # القيمة الافتراضية لليوم
    days_count = db.Column(db.Integer, default=0)
    actual_total = db.Column(db.Float, default=0)
    default_total = db.Column(db.Float, default=0)
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AlMasaCheck(db.Model):
    """شيكات ونش المشاركة"""
    __tablename__ = 'almasa_checks'
    id = db.Column(db.Integer, primary_key=True)
    crane_id = db.Column(db.Integer, db.ForeignKey('almasa_cranes.id'), nullable=False)
    check_number = db.Column(db.String(50))
    company_name = db.Column(db.String(150))
    amount = db.Column(db.Float, default=0)
    due_date = db.Column(db.Date)
    status = db.Column(db.String(20), default='معلق')
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AlMasaCheckOperation(db.Model):
    """ربط الشيك بالعمليات"""
    __tablename__ = 'almasa_check_operations'
    id = db.Column(db.Integer, primary_key=True)
    check_id = db.Column(db.Integer, db.ForeignKey('almasa_checks.id'), nullable=False)
    operation_id = db.Column(db.Integer, db.ForeignKey('almasa_operations.id'), nullable=False)

class AlMasaExpense(db.Model):
    """مصاريف ونش المشاركة"""
    __tablename__ = 'almasa_expenses'
    id = db.Column(db.Integer, primary_key=True)
    crane_id = db.Column(db.Integer, db.ForeignKey('almasa_cranes.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    expense_type = db.Column(db.String(50))
    amount = db.Column(db.Float, default=0)
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# --------------------------------------------------------------------
# النوع 2: ونش خاص (شخص واحد)
# --------------------------------------------------------------------
class AlMasaPrivateCrane(db.Model):
    """ونش خاص - بتاع شخص واحد"""
    __tablename__ = 'almasa_private_cranes'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    owner_name = db.Column(db.String(100), nullable=False)  # اسم صاحب الونش
    notes = db.Column(db.Text)
    operations = db.relationship('AlMasaPrivateOperation', backref='crane', lazy=True, cascade="all, delete-orphan")
    checks = db.relationship('AlMasaPrivateCheck', backref='crane', lazy=True, cascade="all, delete-orphan")
    expenses = db.relationship('AlMasaPrivateExpense', backref='crane', lazy=True, cascade="all, delete-orphan")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AlMasaPrivateOperation(db.Model):
    """عمليات الونش الخاص"""
    __tablename__ = 'almasa_private_operations'
    id = db.Column(db.Integer, primary_key=True)
    crane_id = db.Column(db.Integer, db.ForeignKey('almasa_private_cranes.id'), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date)
    actual_daily_value = db.Column(db.Float, default=0)
    default_daily_value = db.Column(db.Float, default=0)
    days_count = db.Column(db.Integer, default=0)
    actual_total = db.Column(db.Float, default=0)
    default_total = db.Column(db.Float, default=0)
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AlMasaPrivateCheck(db.Model):
    """شيكات الونش الخاص"""
    __tablename__ = 'almasa_private_checks'
    id = db.Column(db.Integer, primary_key=True)
    crane_id = db.Column(db.Integer, db.ForeignKey('almasa_private_cranes.id'), nullable=False)
    check_number = db.Column(db.String(50))
    company_name = db.Column(db.String(150))
    amount = db.Column(db.Float, default=0)
    due_date = db.Column(db.Date)
    status = db.Column(db.String(20), default='معلق')
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AlMasaPrivateCheckOperation(db.Model):
    """ربط شيك الونش الخاص بالعمليات"""
    __tablename__ = 'almasa_private_check_operations'
    id = db.Column(db.Integer, primary_key=True)
    check_id = db.Column(db.Integer, db.ForeignKey('almasa_private_checks.id'), nullable=False)
    operation_id = db.Column(db.Integer, db.ForeignKey('almasa_private_operations.id'), nullable=False)

class AlMasaPrivateExpense(db.Model):
    """مصاريف الونش الخاص"""
    __tablename__ = 'almasa_private_expenses'
    id = db.Column(db.Integer, primary_key=True)
    crane_id = db.Column(db.Integer, db.ForeignKey('almasa_private_cranes.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    expense_type = db.Column(db.String(50))
    amount = db.Column(db.Float, default=0)
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# --------------------------------------------------------------------
# النوع 3: توريدات من خارج لخارج
# --------------------------------------------------------------------
class AlMasaSupply(db.Model):
    """توريدات من خارج لخارج"""
    __tablename__ = 'almasa_supplies'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # اسم التوريدة
    supplier_name = db.Column(db.String(150))  # اسم المورد (اللي بناخد منه)
    customer_name = db.Column(db.String(150))  # اسم العميل (اللي بنديله)
    notes = db.Column(db.Text)
    operations = db.relationship('AlMasaSupplyOperation', backref='supply', lazy=True, cascade="all, delete-orphan")
    expenses = db.relationship('AlMasaSupplyExpense', backref='supply', lazy=True, cascade="all, delete-orphan")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AlMasaSupplyOperation(db.Model):
    """عمليات التوريدات"""
    __tablename__ = 'almasa_supply_operations'
    id = db.Column(db.Integer, primary_key=True)
    supply_id = db.Column(db.Integer, db.ForeignKey('almasa_supplies.id'), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date)
    days_count = db.Column(db.Integer, default=0)
    supplier_daily_rate = db.Column(db.Float, default=0)  # سعر المورد اليومي
    customer_daily_rate = db.Column(db.Float, default=0)  # سعر العميل اليومي
    supplier_total = db.Column(db.Float, default=0)  # إجمالي المورد
    customer_total = db.Column(db.Float, default=0)  # إجمالي العميل
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AlMasaSupplyExpense(db.Model):
    """مصاريف التوريدات"""
    __tablename__ = 'almasa_supply_expenses'
    id = db.Column(db.Integer, primary_key=True)
    supply_id = db.Column(db.Integer, db.ForeignKey('almasa_supplies.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    expense_type = db.Column(db.String(50))
    amount = db.Column(db.Float, default=0)
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# --------------------------------------------------------------------
# حساب الشريك / العميل (منفصل تماماً)
# --------------------------------------------------------------------
class AlMasaPartnerAccount(db.Model):
    """حساب منفصل للشريك أو العميل - بعيد عن الأوناش"""
    __tablename__ = 'almasa_partner_accounts'
    id = db.Column(db.Integer, primary_key=True)
    person_name = db.Column(db.String(100), nullable=False)  # اسم الشريك/العميل
    person_type = db.Column(db.String(20), default='شريك')  # شريك / عميل
    date = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Float, default=0)
    description = db.Column(db.Text)
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# --------------------------------------------------------------------
# تسوية الجرد (المخزن + الخزينة)
# --------------------------------------------------------------------
class AlMasaInventoryAudit(db.Model):
    """تسوية الجرد - مخزن وخزينة"""
    __tablename__ = 'almasa_inventory_audits'
    id = db.Column(db.Integer, primary_key=True)
    audit_date = db.Column(db.Date, nullable=False)
    audit_type = db.Column(db.String(20), nullable=False)  # 'store' / 'treasury' / 'factory'
    item_name = db.Column(db.String(200))
    system_quantity = db.Column(db.Float, default=0)  # الكمية المسجلة
    actual_quantity = db.Column(db.Float, default=0)  # الكمية الفعلية
    difference = db.Column(db.Float, default=0)  # الفرق (ناقص أو زيادة)
    difference_type = db.Column(db.String(20))  # 'ناقص' / 'زيادة' / 'متطابق'
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
