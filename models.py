# models.py
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

# ==================== جدول المستخدمين ====================
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    full_name = db.Column(db.String(100))
    role = db.Column(db.String(20), nullable=False)  # meg, admin, mariam, rehab, mohamed, ahmed, eid, abdo
    phone = db.Column(db.String(20))
    is_hidden = db.Column(db.Boolean, default=False)  # MEG مخفي
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer)  # من أضافه
    last_activity = db.Column(db.DateTime, default=datetime.utcnow)  # آخر نشاط

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


# ==================== الفئات والأصناف ====================
class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)  # كوع، ماسورة، فلانشة...


class Size(db.Model):
    __tablename__ = 'sizes'
    id = db.Column(db.Integer, primary_key=True)
    value = db.Column(db.String(50), unique=True, nullable=False)  # 2"، 4"، 6"...


class Thickness(db.Model):
    __tablename__ = 'thicknesses'
    id = db.Column(db.Integer, primary_key=True)
    value = db.Column(db.String(50), unique=True, nullable=False)  # جدول 40، 5مم...


class Supplier(db.Model):
    __tablename__ = 'suppliers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)
    phone = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Customer(db.Model):
    __tablename__ = 'customers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)
    phone = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ==================== المصنع ====================
class FactoryRawMaterial(db.Model):
    __tablename__ = 'factory_raw_materials'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    pipe_size = db.Column(db.String(50), nullable=False)      # المقاس
    pipe_thickness = db.Column(db.String(50))                 # السماكة
    quantity = db.Column(db.Float, nullable=False)            # عدد المواسير
    supplier = db.Column(db.String(150))                      # اسم المورد
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class FactoryProduction(db.Model):
    __tablename__ = 'factory_production'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    elbow_size = db.Column(db.String(50), nullable=False)     # مقاس الكوع
    elbow_thickness = db.Column(db.String(50))                # سماكة الكوع
    quantity = db.Column(db.Float, nullable=False)            # عدد الأكواع المنتجة
    raw_material_used = db.Column(db.Float)                   # كمية المواسير المستخدمة
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class FactoryDiary(db.Model):
    __tablename__ = 'factory_diary'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    description = db.Column(db.Text, nullable=False)
    amount = db.Column(db.Float, default=0)                   # مصاريف أو قيمة
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ==================== المحل ====================
class StoreSale(db.Model):
    __tablename__ = 'store_sales'
    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(50), unique=True)
    customer_name = db.Column(db.String(150), nullable=False)
    customer_phone = db.Column(db.String(20))
    product_type = db.Column(db.String(100))                   # كوع، ماسورة...
    product_size = db.Column(db.String(50))
    product_spec = db.Column(db.String(50))                    # السماكة أو النوع
    quantity = db.Column(db.Float, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    total = db.Column(db.Float, nullable=False)
    payment_type = db.Column(db.String(20), default='آجل')     # نقدي / آجل
    date = db.Column(db.Date, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class StorePurchase(db.Model):
    __tablename__ = 'store_purchases'
    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(50), unique=True)
    supplier_name = db.Column(db.String(150), nullable=False)
    supplier_phone = db.Column(db.String(20))
    product_type = db.Column(db.String(100))
    product_size = db.Column(db.String(50))
    product_spec = db.Column(db.String(50))
    quantity = db.Column(db.Float, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    total = db.Column(db.Float, nullable=False)
    payment_type = db.Column(db.String(20), default='آجل')     # نقدي / آجل
    date = db.Column(db.Date, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


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
    from_factory = db.Column(db.Boolean, default=True)         # من المصنع
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class StoreReturn(db.Model):
    __tablename__ = 'store_returns'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    return_type = db.Column(db.String(20))  # from_customer / to_supplier
    party_name = db.Column(db.String(150))  # العميل أو المورد
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


# ==================== الخزينة ====================
class TreasuryAccount(db.Model):
    __tablename__ = 'treasury_accounts'
    id = db.Column(db.Integer, primary_key=True)
    person_name = db.Column(db.String(100), nullable=False)   # الحاج أحمد، عيد...
    account_type = db.Column(db.String(20), default='نقدي')   # فودافون كاش / انستا باي / نقدي
    balance = db.Column(db.Float, default=0)

    transactions = db.relationship('TreasuryTransaction', backref='account', lazy=True)


class TreasuryTransaction(db.Model):
    __tablename__ = 'treasury_transactions'
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('treasury_accounts.id'))
    transaction_type = db.Column(db.String(20), nullable=False)  # deposit / withdrawal
    amount = db.Column(db.Float, nullable=False)
    source = db.Column(db.String(150))                        # من / إلى
    payment_method = db.Column(db.String(20))                 # فودافون كاش / انستا باي / نقدي
    date = db.Column(db.Date, nullable=False)
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class TreasuryTransfer(db.Model):
    __tablename__ = 'treasury_transfers'
    id = db.Column(db.Integer, primary_key=True)
    from_person = db.Column(db.String(100), nullable=False)
    to_person = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(20))
    date = db.Column(db.Date, nullable=False)
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ==================== سجلات التعديل ====================
class EditLog(db.Model):
    __tablename__ = 'edit_logs'
    id = db.Column(db.Integer, primary_key=True)
    record_type = db.Column(db.String(50))  # factory_raw_material, store_sale...
    record_id = db.Column(db.Integer)
    edited_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    edit_date = db.Column(db.DateTime, default=datetime.utcnow)
    old_data = db.Column(db.Text)
    new_data = db.Column(db.Text)
    notes = db.Column(db.Text)


# ==================== التنبيهات ====================
class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))  # المستخدم المستلم
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ==================== سجل النشاط ====================
class ActivityLog(db.Model):
    __tablename__ = 'activity_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    action = db.Column(db.String(100), nullable=False)  # login, logout, create, edit, delete
    details = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='activities')
