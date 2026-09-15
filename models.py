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

# ==================== التصنيفات ====================
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

class InventoryAudit(db.Model):
    __tablename__ = 'inventory_audits'
    id = db.Column(db.Integer, primary_key=True)
    audit_date = db.Column(db.Date, nullable=False)
    audit_type = db.Column(db.String(20), nullable=False)
    item_name = db.Column(db.String(200))
    item_size = db.Column(db.String(50))
    item_spec = db.Column(db.String(50))
    account_type = db.Column(db.String(50))
    system_quantity = db.Column(db.Float, default=0)
    actual_quantity = db.Column(db.Float, default=0)
    difference = db.Column(db.Float, default=0)
    difference_type = db.Column(db.String(20))
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ====================================================================
# ==================== الشات ====================
# ====================================================================

class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey('users.id'))  # للشات الفردي
    group_id = db.Column(db.Integer, db.ForeignKey('chat_groups.id'))  # للشات الجماعي
    message = db.Column(db.Text)  # ممكن يكون NULL لو الرسالة محذوفة
    is_deleted = db.Column(db.Boolean, default=False)  # علامة "تم الحذف"
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_messages')
    recipient = db.relationship('User', foreign_keys=[recipient_id], backref='received_messages')

    @property
    def display_message(self):
        if self.is_deleted:
            return '🚫 تم حذف هذه الرسالة'
        return self.message or ''

class ChatGroup(db.Model):
    __tablename__ = 'chat_groups'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    members = db.relationship('ChatGroupMember', backref='group', lazy=True, cascade='all, delete-orphan')
    messages = db.relationship('ChatMessage', backref='group', lazy=True, cascade='all, delete-orphan')

class ChatGroupMember(db.Model):
    __tablename__ = 'chat_group_members'
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('chat_groups.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref='chat_groups')

# ====================================================================
# ==================== شركة الماسة ====================
# ====================================================================

# --------------------------------------------------------------------
# النوع 1: ونش مشاركة
# --------------------------------------------------------------------
class AlMasaCrane(db.Model):
    __tablename__ = 'almasa_cranes'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    notes = db.Column(db.Text)
    crane_type = db.Column(db.String(20), default='partnership')
    partners = db.relationship('AlMasaPartner', backref='crane', lazy=True, cascade="all, delete-orphan")
    operations = db.relationship('AlMasaOperation', backref='crane', lazy=True, cascade="all, delete-orphan")
    checks = db.relationship('AlMasaCheck', backref='crane', lazy=True, cascade="all, delete-orphan")
    expenses = db.relationship('AlMasaExpense', backref='crane', lazy=True, cascade="all, delete-orphan")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AlMasaPartner(db.Model):
    __tablename__ = 'almasa_partners'
    id = db.Column(db.Integer, primary_key=True)
    crane_id = db.Column(db.Integer, db.ForeignKey('almasa_cranes.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    percentage = db.Column(db.Float, default=0)
    is_basic = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AlMasaOperation(db.Model):
    __tablename__ = 'almasa_operations'
    id = db.Column(db.Integer, primary_key=True)
    crane_id = db.Column(db.Integer, db.ForeignKey('almasa_cranes.id'), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date)
    supply_value = db.Column(db.Float, default=0)
    rental_value = db.Column(db.Float, default=0)
    supply_total = db.Column(db.Float, default=0)
    rental_total = db.Column(db.Float, default=0)
    days_count = db.Column(db.Integer, default=0)
    extra_hours = db.Column(db.Float, default=0)
    hour_rate = db.Column(db.Float, default=0)
    travel_days = db.Column(db.Float, default=0)
    travel_rate = db.Column(db.Float, default=0)
    tax_14_enabled = db.Column(db.Boolean, default=False)
    tax_14_value = db.Column(db.Float, default=14)
    tax_85_enabled = db.Column(db.Boolean, default=False)
    tax_85_value = db.Column(db.Float, default=8.5)
    invoice_number = db.Column(db.String(50))
    invoice_date = db.Column(db.Date)
    project_name = db.Column(db.String(200))
    project_location = db.Column(db.String(200))
    payment_method = db.Column(db.String(20))
    check_received = db.Column(db.Boolean, default=False)
    check_received_date = db.Column(db.Date)
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AlMasaCheck(db.Model):
    __tablename__ = 'almasa_checks'
    id = db.Column(db.Integer, primary_key=True)
    crane_id = db.Column(db.Integer, db.ForeignKey('almasa_cranes.id'), nullable=False)
    operation_id = db.Column(db.Integer, db.ForeignKey('almasa_operations.id'))
    check_number = db.Column(db.String(50))
    company_name = db.Column(db.String(150))
    amount = db.Column(db.Float, default=0)
    issue_date = db.Column(db.Date)
    due_date = db.Column(db.Date)
    status = db.Column(db.String(20), default='معلق')
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AlMasaCheckOperation(db.Model):
    __tablename__ = 'almasa_check_operations'
    id = db.Column(db.Integer, primary_key=True)
    check_id = db.Column(db.Integer, db.ForeignKey('almasa_checks.id'), nullable=False)
    operation_id = db.Column(db.Integer, db.ForeignKey('almasa_operations.id'), nullable=False)

class AlMasaExpense(db.Model):
    __tablename__ = 'almasa_expenses'
    id = db.Column(db.Integer, primary_key=True)
    crane_id = db.Column(db.Integer, db.ForeignKey('almasa_cranes.id'), nullable=False)
    operation_id = db.Column(db.Integer, db.ForeignKey('almasa_operations.id'))
    date = db.Column(db.Date, nullable=False)
    expense_type = db.Column(db.String(50))
    amount = db.Column(db.Float, default=0)
    paid_by = db.Column(db.String(100))
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# --------------------------------------------------------------------
# النوع 2: ونش خاص
# --------------------------------------------------------------------
class AlMasaPrivateCrane(db.Model):
    __tablename__ = 'almasa_private_cranes'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    owner_name = db.Column(db.String(100), nullable=False)
    notes = db.Column(db.Text)
    operations = db.relationship('AlMasaPrivateOperation', backref='crane', lazy=True, cascade="all, delete-orphan")
    checks = db.relationship('AlMasaPrivateCheck', backref='crane', lazy=True, cascade="all, delete-orphan")
    expenses = db.relationship('AlMasaPrivateExpense', backref='crane', lazy=True, cascade="all, delete-orphan")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AlMasaPrivateOperation(db.Model):
    __tablename__ = 'almasa_private_operations'
    id = db.Column(db.Integer, primary_key=True)
    crane_id = db.Column(db.Integer, db.ForeignKey('almasa_private_cranes.id'), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date)
    supply_value = db.Column(db.Float, default=0)
    rental_value = db.Column(db.Float, default=0)
    supply_total = db.Column(db.Float, default=0)
    rental_total = db.Column(db.Float, default=0)
    days_count = db.Column(db.Integer, default=0)
    extra_hours = db.Column(db.Float, default=0)
    hour_rate = db.Column(db.Float, default=0)
    travel_days = db.Column(db.Float, default=0)
    travel_rate = db.Column(db.Float, default=0)
    tax_14_enabled = db.Column(db.Boolean, default=False)
    tax_14_value = db.Column(db.Float, default=14)
    tax_85_enabled = db.Column(db.Boolean, default=False)
    tax_85_value = db.Column(db.Float, default=8.5)
    invoice_number = db.Column(db.String(50))
    invoice_date = db.Column(db.Date)
    project_name = db.Column(db.String(200))
    project_location = db.Column(db.String(200))
    payment_method = db.Column(db.String(20))
    check_received = db.Column(db.Boolean, default=False)
    check_received_date = db.Column(db.Date)
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AlMasaPrivateCheck(db.Model):
    __tablename__ = 'almasa_private_checks'
    id = db.Column(db.Integer, primary_key=True)
    crane_id = db.Column(db.Integer, db.ForeignKey('almasa_private_cranes.id'), nullable=False)
    operation_id = db.Column(db.Integer, db.ForeignKey('almasa_private_operations.id'))
    check_number = db.Column(db.String(50))
    company_name = db.Column(db.String(150))
    amount = db.Column(db.Float, default=0)
    issue_date = db.Column(db.Date)
    due_date = db.Column(db.Date)
    status = db.Column(db.String(20), default='معلق')
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AlMasaPrivateCheckOperation(db.Model):
    __tablename__ = 'almasa_private_check_operations'
    id = db.Column(db.Integer, primary_key=True)
    check_id = db.Column(db.Integer, db.ForeignKey('almasa_private_checks.id'), nullable=False)
    operation_id = db.Column(db.Integer, db.ForeignKey('almasa_private_operations.id'), nullable=False)

class AlMasaPrivateExpense(db.Model):
    __tablename__ = 'almasa_private_expenses'
    id = db.Column(db.Integer, primary_key=True)
    crane_id = db.Column(db.Integer, db.ForeignKey('almasa_private_cranes.id'), nullable=False)
    operation_id = db.Column(db.Integer, db.ForeignKey('almasa_private_operations.id'))
    date = db.Column(db.Date, nullable=False)
    expense_type = db.Column(db.String(50))
    amount = db.Column(db.Float, default=0)
    paid_by = db.Column(db.String(100))
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# --------------------------------------------------------------------
# النوع 3: توريدات
# --------------------------------------------------------------------
class AlMasaSupply(db.Model):
    __tablename__ = 'almasa_supplies'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    supplier_name = db.Column(db.String(150))
    customer_name = db.Column(db.String(150))
    notes = db.Column(db.Text)
    operations = db.relationship('AlMasaSupplyOperation', backref='supply', lazy=True, cascade="all, delete-orphan")
    expenses = db.relationship('AlMasaSupplyExpense', backref='supply', lazy=True, cascade="all, delete-orphan")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AlMasaSupplyOperation(db.Model):
    __tablename__ = 'almasa_supply_operations'
    id = db.Column(db.Integer, primary_key=True)
    supply_id = db.Column(db.Integer, db.ForeignKey('almasa_supplies.id'), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date)
    days_count = db.Column(db.Integer, default=0)
    supply_value = db.Column(db.Float, default=0)
    rental_value = db.Column(db.Float, default=0)
    supply_total = db.Column(db.Float, default=0)
    rental_total = db.Column(db.Float, default=0)
    extra_hours = db.Column(db.Float, default=0)
    hour_rate = db.Column(db.Float, default=0)
    travel_days = db.Column(db.Float, default=0)
    travel_rate = db.Column(db.Float, default=0)
    tax_14_enabled = db.Column(db.Boolean, default=False)
    tax_14_value = db.Column(db.Float, default=14)
    tax_85_enabled = db.Column(db.Boolean, default=False)
    tax_85_value = db.Column(db.Float, default=8.5)
    invoice_number = db.Column(db.String(50))
    invoice_date = db.Column(db.Date)
    project_name = db.Column(db.String(200))
    project_location = db.Column(db.String(200))
    payment_method = db.Column(db.String(20))
    check_received = db.Column(db.Boolean, default=False)
    check_received_date = db.Column(db.Date)
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AlMasaSupplyExpense(db.Model):
    __tablename__ = 'almasa_supply_expenses'
    id = db.Column(db.Integer, primary_key=True)
    supply_id = db.Column(db.Integer, db.ForeignKey('almasa_supplies.id'), nullable=False)
    operation_id = db.Column(db.Integer, db.ForeignKey('almasa_supply_operations.id'))
    date = db.Column(db.Date, nullable=False)
    expense_type = db.Column(db.String(50))
    amount = db.Column(db.Float, default=0)
    paid_by = db.Column(db.String(100))
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# --------------------------------------------------------------------
# حساب الشريك / العميل
# --------------------------------------------------------------------
class AlMasaPartnerAccount(db.Model):
    __tablename__ = 'almasa_partner_accounts'
    id = db.Column(db.Integer, primary_key=True)
    person_name = db.Column(db.String(100), nullable=False)
    person_type = db.Column(db.String(20), default='شريك')
    date = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Float, default=0)
    description = db.Column(db.Text)
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
