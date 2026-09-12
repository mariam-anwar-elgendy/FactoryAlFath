# app.py
import os
from datetime import datetime, date, timedelta
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

from models import (
    db, User, Category, Size, Thickness, Supplier, Customer,
    FactoryRawMaterial, FactoryProduction, FactoryDiary,
    StoreSale, StorePurchase, StoreInventory, StoreReceiving, StoreReturn, StoreDiary,
    StoreSaleItem, StorePurchaseItem, Payment,
    TreasuryAccount, TreasuryTransaction, TreasuryTransfer,
    EditLog, Notification, ActivityLog,
    InventoryAudit,
    AlMasaCrane, AlMasaPartner, AlMasaOperation, AlMasaCheck, AlMasaCheckOperation, AlMasaExpense,
    AlMasaPrivateCrane, AlMasaPrivateOperation, AlMasaPrivateCheck, AlMasaPrivateCheckOperation, AlMasaPrivateExpense,
    AlMasaSupply, AlMasaSupplyOperation, AlMasaSupplyExpense,
    AlMasaPartnerAccount
)
from utils import (
    login_required as custom_login_required,
    role_required,
    can_edit,
    add_row_to_excel,
    generate_word_report,
    GoogleDriveService
)

app = Flask(__name__)

# ==================== إعدادات الجلسة ====================
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-me')
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = '/tmp/flask_session'
app.config['SESSION_PERMANENT'] = True
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

# ==================== قاعدة البيانات ====================
database_url = os.environ.get('DATABASE_URL', 'sqlite:///instance/factory.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_timeout': 30,
    'pool_recycle': 300
}

db.init_app(app)

# ==================== Flask-Login ====================
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'يرجى تسجيل الدخول أولاً'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ==================== خدمة Google Drive ====================
drive_service = GoogleDriveService(
    credentials_file=os.environ.get('GOOGLE_CREDENTIALS_FILE', 'client_secrets.json'),
    folder_id=os.environ.get('GOOGLE_DRIVE_FOLDER_ID', '')
)

# ==================== دوال مساعدة ====================
def get_or_create_treasury_account(person_name, account_type):
    account = TreasuryAccount.query.filter_by(person_name=person_name, account_type=account_type).first()
    if not account:
        account = TreasuryAccount(person_name=person_name, account_type=account_type, balance=0)
        db.session.add(account)
        db.session.commit()
    return account

def get_visible_accounts_for_current_user():
    if current_user.role in ['meg', 'admin', 'mariam', 'sayed']:
        return TreasuryAccount.query.all()
    elif current_user.role == 'ahmed':
        return TreasuryAccount.query.filter_by(person_name='الحاج أحمد').all()
    elif current_user.role == 'eid':
        return TreasuryAccount.query.filter_by(person_name='عيد').all()
    elif current_user.role == 'abdo':
        return TreasuryAccount.query.filter_by(person_name='عبدالله').all()
    else:
        return []

def can_delete_record(user_role, record_date=None):
    if user_role in ['meg', 'admin', 'mariam', 'sayed']:
        return True
    if user_role == 'rehab':
        if record_date:
            return (datetime.now().date() - record_date).days <= 7
        return False
    return False

def log_activity(user_id, action, details=''):
    try:
        activity = ActivityLog(user_id=user_id, action=action, details=details, timestamp=datetime.utcnow())
        db.session.add(activity)
        user = User.query.get(user_id)
        if user:
            user.last_activity = datetime.utcnow()
            db.session.add(user)
        db.session.commit()
    except Exception as e:
        print(f"Error logging activity: {e}")

# ==================== تهيئة قاعدة البيانات ====================
def init_db():
    with app.app_context():
        db.create_all()
        
        # تحديث هيكل قاعدة البيانات تلقائياً
        try:
            db.session.execute(db.text('ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR(20)'))
            db.session.execute(db.text('ALTER TABLE users ADD COLUMN IF NOT EXISTS last_activity TIMESTAMP'))
            db.session.execute(db.text('ALTER TABLE store_receiving ADD COLUMN IF NOT EXISTS supplier VARCHAR(100)'))
            db.session.commit()
            print("✅ تم إضافة الحقول الجديدة")
        except Exception as e:
            db.session.rollback()
            print(f"⚠️ ملاحظة الحقول: {e}")
        
        try:
            db.session.execute(db.text('ALTER TABLE store_sales DROP COLUMN IF EXISTS product_type CASCADE'))
            db.session.execute(db.text('ALTER TABLE store_sales DROP COLUMN IF EXISTS product_size CASCADE'))
            db.session.execute(db.text('ALTER TABLE store_sales DROP COLUMN IF EXISTS product_spec CASCADE'))
            db.session.execute(db.text('ALTER TABLE store_sales DROP COLUMN IF EXISTS quantity CASCADE'))
            db.session.execute(db.text('ALTER TABLE store_sales DROP COLUMN IF EXISTS unit_price CASCADE'))
            db.session.execute(db.text('ALTER TABLE store_sales DROP COLUMN IF EXISTS total CASCADE'))
            db.session.execute(db.text('ALTER TABLE store_sales DROP COLUMN IF EXISTS paid_amount CASCADE'))
            db.session.execute(db.text('ALTER TABLE store_sales DROP COLUMN IF EXISTS remaining_amount CASCADE'))
            db.session.commit()
        except Exception as e:
            db.session.rollback()
        
        try:
            db.session.execute(db.text('ALTER TABLE store_purchases DROP COLUMN IF EXISTS product_type CASCADE'))
            db.session.execute(db.text('ALTER TABLE store_purchases DROP COLUMN IF EXISTS product_size CASCADE'))
            db.session.execute(db.text('ALTER TABLE store_purchases DROP COLUMN IF EXISTS product_spec CASCADE'))
            db.session.execute(db.text('ALTER TABLE store_purchases DROP COLUMN IF EXISTS quantity CASCADE'))
            db.session.execute(db.text('ALTER TABLE store_purchases DROP COLUMN IF EXISTS unit_price CASCADE'))
            db.session.execute(db.text('ALTER TABLE store_purchases DROP COLUMN IF EXISTS total CASCADE'))
            db.session.execute(db.text('ALTER TABLE store_purchases DROP COLUMN IF EXISTS paid_amount CASCADE'))
            db.session.execute(db.text('ALTER TABLE store_purchases DROP COLUMN IF EXISTS remaining_amount CASCADE'))
            db.session.commit()
        except Exception as e:
            db.session.rollback()

        users_data = [
            {'username': 'meg', 'password': '262004', 'full_name': 'MEG', 'role': 'meg', 'is_hidden': True},
            {'username': 'f', 'password': '*1997#', 'full_name': 'Admin', 'role': 'admin', 'is_hidden': False},
            {'username': 'mariam', 'password': '#mariam2004', 'full_name': 'Mariam', 'role': 'mariam', 'is_hidden': False},
            {'username': 'rehab', 'password': 'rehab2004#', 'full_name': 'Rehab', 'role': 'rehab', 'is_hidden': False},
            {'username': 'mohamed', 'password': 'mohamed123#', 'full_name': 'Mohamed', 'role': 'mohamed', 'is_hidden': False},
            {'username': 'a', 'password': '#123456#', 'full_name': 'الحاج أحمد', 'role': 'ahmed', 'is_hidden': False},
            {'username': 'eid', 'password': 'eid123#', 'full_name': 'عيد', 'role': 'eid', 'is_hidden': False},
            {'username': 'abdo', 'password': 'abdo123#', 'full_name': 'عبدالله', 'role': 'abdo', 'is_hidden': False},
            {'username': 'sayed', 'password': 'sayed1977#', 'full_name': 'سيد', 'role': 'sayed', 'is_hidden': False},
            {'username': 'dina', 'password': 'dina2003', 'full_name': 'دينا', 'role': 'dina', 'is_hidden': False},
        ]

        for user_data in users_data:
            existing_user = User.query.filter_by(username=user_data['username']).first()
            if not existing_user:
                new_user = User(
                    username=user_data['username'],
                    full_name=user_data['full_name'],
                    role=user_data['role'],
                    is_hidden=user_data['is_hidden'],
                    created_at=datetime.utcnow()
                )
                new_user.set_password(user_data['password'])
                db.session.add(new_user)

        db.session.commit()
        print("✅ تم تهيئة قاعدة البيانات وإنشاء المستخدمين")

        treasury_persons = ['الحاج أحمد', 'عيد', 'عبدالله', 'الحاج فتحي']
        account_types = ['كاش', 'فودافون كاش', 'انستا باي', 'شيك']
        for person in treasury_persons:
            for acc_type in account_types:
                get_or_create_treasury_account(person, acc_type)

        print("✅ تم إنشاء حسابات الخزينة")

init_db()

# ==================== Context Processor ====================
@app.context_processor
def inject_globals():
    unread_notifications = 0
    if current_user.is_authenticated:
        unread_notifications = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    def get_user_name(user_id):
        if not user_id:
            return 'غير معروف'
        user = User.query.get(user_id)
        return user.full_name if user else 'غير معروف'
    return {'now': datetime.now(), 'unread_notifications': unread_notifications, 'get_user_name': get_user_name}

# ==================== الصفحات الأساسية ====================
@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'message': 'مصنع الفتح شغال'})

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            session.permanent = True
            session['role'] = user.role
            session['user_id'] = user.id
            session['full_name'] = user.full_name
            log_activity(user.id, 'login', f"تسجيل دخول {user.full_name}")
            flash(f'مرحباً {user.full_name} 👋', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('اسم المستخدم أو كلمة المرور غير صحيحة', 'danger')
    return render_template('login.html')

@app.route('/choose-company')
@custom_login_required
def choose_company():
    if current_user.role != 'sayed':
        return redirect(url_for('dashboard'))
    return render_template('choose_company.html')

@app.route('/logout')
@login_required
def logout():
    log_activity(current_user.id, 'logout', f"تسجيل خروج {current_user.full_name}")
    logout_user()
    session.clear()
    flash('تم تسجيل الخروج بنجاح', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@custom_login_required
def dashboard():
    role = current_user.role
    if role == 'dina':
        return redirect(url_for('almasa_index'))
    
    stats = {
        'raw_materials_count': FactoryRawMaterial.query.count() if role in ['meg','admin','mariam','rehab','mohamed','sayed'] else 0,
        'production_count': FactoryProduction.query.count() if role in ['meg','admin','mariam','rehab','mohamed','sayed'] else 0,
        'sales_count': StoreSale.query.count() if role in ['meg','admin','mariam','rehab','ahmed','sayed'] else 0,
        'purchases_count': StorePurchase.query.count() if role in ['meg','admin','mariam','rehab','ahmed','sayed'] else 0,
        'customers_count': Customer.query.count() if role in ['meg','admin','mariam','rehab','ahmed','sayed'] else 0,
        'suppliers_count': Supplier.query.count() if role in ['meg','admin','mariam','rehab','ahmed','sayed'] else 0,
        'treasury_balance': 0,
        'today_sales': db.session.query(db.func.sum(StoreSaleItem.total)).join(StoreSale).filter(StoreSale.date == date.today()).scalar() or 0,
        'today_purchases': db.session.query(db.func.sum(StorePurchaseItem.total)).join(StorePurchase).filter(StorePurchase.date == date.today()).scalar() or 0,
        'low_inventory_count': StoreInventory.query.filter(StoreInventory.current_quantity <= StoreInventory.min_quantity).count() if role in ['meg','admin','mariam','rehab','ahmed','sayed'] else 0,
    }

    if role in ['meg', 'admin', 'mariam', 'sayed']:
        stats['treasury_balance'] = db.session.query(db.func.sum(TreasuryAccount.balance)).scalar() or 0
        recent_sales = StoreSale.query.order_by(StoreSale.date.desc()).limit(5).all()
        recent_production = FactoryProduction.query.order_by(FactoryProduction.date.desc()).limit(5).all()
        recent_transactions = TreasuryTransaction.query.order_by(TreasuryTransaction.date.desc()).limit(5).all()
    elif role == 'rehab':
        stats['treasury_balance'] = 0
        recent_sales = StoreSale.query.order_by(StoreSale.date.desc()).limit(5).all()
        recent_production = FactoryProduction.query.order_by(FactoryProduction.date.desc()).limit(5).all()
        recent_transactions = []
    elif role == 'mohamed':
        stats['treasury_balance'] = 0
        recent_sales = []
        recent_production = FactoryProduction.query.order_by(FactoryProduction.date.desc()).limit(5).all()
        recent_transactions = []
    elif role == 'ahmed':
        stats['treasury_balance'] = db.session.query(db.func.sum(TreasuryAccount.balance)).filter(TreasuryAccount.person_name == current_user.full_name).scalar() or 0
        recent_sales = StoreSale.query.order_by(StoreSale.date.desc()).limit(5).all()
        recent_production = []
        recent_transactions = TreasuryTransaction.query.filter_by(created_by=current_user.id).order_by(TreasuryTransaction.date.desc()).limit(5).all()
    else:
        stats['treasury_balance'] = db.session.query(db.func.sum(TreasuryAccount.balance)).filter(TreasuryAccount.person_name == current_user.full_name).scalar() or 0
        recent_sales = []
        recent_production = []
        recent_transactions = TreasuryTransaction.query.filter_by(created_by=current_user.id).order_by(TreasuryTransaction.date.desc()).limit(5).all()

    inactive_users_count = 0
    if role == 'admin':
        threshold = datetime.utcnow() - timedelta(days=3)
        inactive_users_count = User.query.filter(User.is_hidden == False, User.last_activity < threshold).count()

    return render_template('dashboard.html', stats=stats,
                           recent_sales=recent_sales,
                           recent_production=recent_production,
                           recent_transactions=recent_transactions,
                           inactive_users_count=inactive_users_count)

# ==================== المصنع ====================
@app.route('/factory')
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab', 'mohamed', 'sayed')
def factory_index():
    today = date.today()
    raw_materials = FactoryRawMaterial.query.filter_by(date=today).order_by(FactoryRawMaterial.id.asc()).all()
    production = FactoryProduction.query.filter_by(date=today).order_by(FactoryProduction.id.asc()).all()
    diary = FactoryDiary.query.filter_by(date=today).order_by(FactoryDiary.id.asc()).all()
    return render_template('factory/index.html', raw_materials=raw_materials, production=production, diary=diary)

@app.route('/factory/raw-materials', methods=['GET', 'POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab', 'mohamed', 'sayed')
def factory_raw_materials():
    if request.method == 'POST':
        if request.form.get('delete_id'):
            record_id = int(request.form.get('delete_id'))
            record = FactoryRawMaterial.query.get_or_404(record_id)
            if can_delete_record(current_user.role, record.date):
                db.session.delete(record)
                db.session.commit()
                flash('تم حذف السجل بنجاح', 'success')
            else:
                flash('غير مصرح لك بالحذف', 'danger')
            return redirect(url_for('factory_raw_materials'))
        if request.form.get('edit_id'):
            record_id = int(request.form.get('edit_id'))
            record = FactoryRawMaterial.query.get_or_404(record_id)
            if can_edit(current_user.role, record.date, record.created_by, current_user.id):
                record.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
                record.pipe_size = request.form.get('pipe_size')
                record.pipe_thickness = request.form.get('pipe_thickness')
                record.quantity = float(request.form.get('quantity', 0))
                record.supplier = request.form.get('supplier')
                record.notes = request.form.get('notes')
                db.session.commit()
                flash('تم تحديث السجل بنجاح', 'success')
            return redirect(url_for('factory_raw_materials'))
        record_date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        pipe_size = request.form.get('pipe_size')
        pipe_thickness = request.form.get('pipe_thickness')
        quantity = float(request.form.get('quantity', 0))
        supplier = request.form.get('supplier')
        notes = request.form.get('notes')
        if supplier and not Supplier.query.filter_by(name=supplier).first():
            db.session.add(Supplier(name=supplier))
        new_record = FactoryRawMaterial(date=record_date, pipe_size=pipe_size, pipe_thickness=pipe_thickness,
                                        quantity=quantity, supplier=supplier, notes=notes,
                                        created_by=current_user.id, created_at=datetime.utcnow())
        db.session.add(new_record)
        db.session.commit()
        flash('تم إضافة وارد المواسير بنجاح', 'success')
        return redirect(url_for('factory_raw_materials'))
    materials = FactoryRawMaterial.query.order_by(FactoryRawMaterial.date.asc(), FactoryRawMaterial.id.asc()).all()
    suppliers = Supplier.query.order_by(Supplier.name.asc()).all()
    return render_template('factory/raw_materials.html', materials=materials, suppliers=suppliers)

@app.route('/factory/production', methods=['GET', 'POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab', 'mohamed', 'sayed')
def factory_production():
    if request.method == 'POST':
        if request.form.get('delete_id'):
            record_id = int(request.form.get('delete_id'))
            record = FactoryProduction.query.get_or_404(record_id)
            if can_delete_record(current_user.role, record.date):
                db.session.delete(record)
                db.session.commit()
                flash('تم حذف السجل بنجاح', 'success')
            return redirect(url_for('factory_production'))
        if request.form.get('edit_id'):
            record_id = int(request.form.get('edit_id'))
            record = FactoryProduction.query.get_or_404(record_id)
            if can_edit(current_user.role, record.date, record.created_by, current_user.id):
                record.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
                record.elbow_size = request.form.get('elbow_size')
                record.elbow_thickness = request.form.get('elbow_thickness')
                record.quantity = float(request.form.get('quantity', 0))
                record.raw_material_used = float(request.form.get('raw_material_used', 0))
                record.notes = request.form.get('notes')
                db.session.commit()
                flash('تم تحديث السجل بنجاح', 'success')
            return redirect(url_for('factory_production'))
        record_date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        elbow_size = request.form.get('elbow_size')
        elbow_thickness = request.form.get('elbow_thickness')
        quantity = float(request.form.get('quantity', 0))
        raw_material_used = float(request.form.get('raw_material_used', 0))
        notes = request.form.get('notes')
        new_record = FactoryProduction(date=record_date, elbow_size=elbow_size, elbow_thickness=elbow_thickness,
                                       quantity=quantity, raw_material_used=raw_material_used, notes=notes,
                                       created_by=current_user.id, created_at=datetime.utcnow())
        db.session.add(new_record)
        db.session.commit()
        flash('تم تسجيل الإنتاج بنجاح', 'success')
        return redirect(url_for('factory_production'))
    production = FactoryProduction.query.order_by(FactoryProduction.date.asc(), FactoryProduction.id.asc()).all()
    return render_template('factory/production.html', production=production)

@app.route('/factory/diary', methods=['GET', 'POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab', 'mohamed', 'sayed')
def factory_diary():
    if request.method == 'POST':
        if request.form.get('delete_id'):
            record_id = int(request.form.get('delete_id'))
            record = FactoryDiary.query.get_or_404(record_id)
            if can_delete_record(current_user.role, record.date):
                db.session.delete(record)
                db.session.commit()
                flash('تم حذف السجل بنجاح', 'success')
            return redirect(url_for('factory_diary'))
        if request.form.get('edit_id'):
            record_id = int(request.form.get('edit_id'))
            record = FactoryDiary.query.get_or_404(record_id)
            if can_edit(current_user.role, record.date, record.created_by, current_user.id):
                record.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
                record.description = request.form.get('description')
                record.amount = float(request.form.get('amount', 0))
                db.session.commit()
                flash('تم تحديث السجل بنجاح', 'success')
            return redirect(url_for('factory_diary'))
        record_date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        descriptions = request.form.getlist('description[]')
        amounts = request.form.getlist('amount[]')
        for i in range(len(descriptions)):
            if descriptions[i].strip():
                new_record = FactoryDiary(date=record_date, description=descriptions[i],
                                          amount=float(amounts[i]) if i < len(amounts) and amounts[i] else 0,
                                          created_by=current_user.id, created_at=datetime.utcnow())
                db.session.add(new_record)
        db.session.commit()
        flash('تم تسجيل اليومية بنجاح', 'success')
        return redirect(url_for('factory_diary'))
    diary = FactoryDiary.query.order_by(FactoryDiary.date.asc(), FactoryDiary.id.asc()).all()
    return render_template('factory/diary.html', diary=diary)

# ==================== المحل ====================
@app.route('/store')
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab', 'ahmed', 'sayed')
def store_index():
    today = date.today()
    sales = StoreSale.query.filter_by(date=today).order_by(StoreSale.id.asc()).all()
    purchases = StorePurchase.query.filter_by(date=today).order_by(StorePurchase.id.asc()).all()
    receiving = StoreReceiving.query.filter_by(date=today).order_by(StoreReceiving.id.asc()).all()
    inventory_low = StoreInventory.query.filter(StoreInventory.current_quantity <= StoreInventory.min_quantity).count()
    return render_template('store/index.html', sales=sales, purchases=purchases, receiving=receiving, inventory_low=inventory_low)

@app.route('/store/transactions', methods=['GET', 'POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab', 'ahmed', 'sayed')
def store_transactions():
    if request.method == 'POST':
        if request.form.get('delete_id'):
            record_id = int(request.form.get('delete_id'))
            transaction_type = request.form.get('transaction_type')
            if can_delete_record(current_user.role, StoreSale.query.get_or_404(record_id).date if transaction_type == 'sale' else StorePurchase.query.get_or_404(record_id).date):
                if transaction_type == 'sale':
                    record = StoreSale.query.get_or_404(record_id)
                    for item in record.items:
                        inv = StoreInventory.query.filter_by(product_type=item.product_type,
                                                             product_size=item.product_size,
                                                             product_spec=item.product_spec).first()
                        if inv:
                            inv.current_quantity += item.quantity
                    db.session.delete(record)
                    db.session.commit()
                    flash('تم الحذف بنجاح', 'success')
                elif transaction_type == 'purchase':
                    record = StorePurchase.query.get_or_404(record_id)
                    for item in record.items:
                        inv = StoreInventory.query.filter_by(product_type=item.product_type,
                                                             product_size=item.product_size,
                                                             product_spec=item.product_spec).first()
                        if inv:
                            inv.current_quantity -= item.quantity
                    db.session.delete(record)
                    db.session.commit()
                    flash('تم الحذف بنجاح', 'success')
            return redirect(url_for('store_transactions'))

        if request.form.get('edit_id'):
            record_id = int(request.form.get('edit_id'))
            transaction_type = request.form.get('transaction_type')
            if transaction_type == 'sale':
                record = StoreSale.query.get_or_404(record_id)
                if can_edit(current_user.role, record.date, record.created_by, current_user.id):
                    record.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
                    record.customer_name = request.form.get('party_name')
                    record.customer_phone = request.form.get('party_phone')
                    record.payment_type = request.form.get('payment_type', 'آجل')
                    for item in record.items:
                        inv = StoreInventory.query.filter_by(product_type=item.product_type,
                                                             product_size=item.product_size,
                                                             product_spec=item.product_spec).first()
                        if inv:
                            inv.current_quantity += item.quantity
                        db.session.delete(item)
                    product_types = request.form.getlist('product_type')
                    product_sizes = request.form.getlist('product_size')
                    product_specs = request.form.getlist('product_spec')
                    quantities = request.form.getlist('quantity')
                    unit_prices = request.form.getlist('unit_price')
                    new_product_types = request.form.getlist('new_product_type')
                    new_product_sizes = request.form.getlist('new_product_size')
                    new_product_specs = request.form.getlist('new_product_spec')
                    for i in range(len(product_types)):
                        if not product_types[i].strip() or not quantities[i].strip():
                            continue
                        product_type = product_types[i]
                        if product_type == 'new':
                            product_type = new_product_types[i] if i < len(new_product_types) else ''
                            if product_type and not Category.query.filter_by(name=product_type).first():
                                db.session.add(Category(name=product_type))
                        product_size = product_sizes[i] if i < len(product_sizes) else ''
                        if product_size == 'new':
                            product_size = new_product_sizes[i] if i < len(new_product_sizes) else ''
                            if product_size and not Size.query.filter_by(value=product_size).first():
                                db.session.add(Size(value=product_size))
                        product_spec = product_specs[i] if i < len(product_specs) else ''
                        if product_spec == 'new':
                            product_spec = new_product_specs[i] if i < len(new_product_specs) else ''
                            if product_spec and not Thickness.query.filter_by(value=product_spec).first():
                                db.session.add(Thickness(value=product_spec))
                        item = StoreSaleItem(
                            sale_id=record.id,
                            product_type=product_type,
                            product_size=product_size,
                            product_spec=product_spec,
                            quantity=float(quantities[i]) if quantities[i] else 0,
                            unit_price=float(unit_prices[i]) if unit_prices[i] else 0,
                        )
                        item.total = item.quantity * item.unit_price
                        db.session.add(item)
                        inv = StoreInventory.query.filter_by(product_type=item.product_type,
                                                             product_size=item.product_size,
                                                             product_spec=item.product_spec).first()
                        if inv:
                            inv.current_quantity -= item.quantity
                        else:
                            inv = StoreInventory(product_type=item.product_type,
                                                 product_size=item.product_size,
                                                 product_spec=item.product_spec,
                                                 current_quantity=-item.quantity)
                            db.session.add(inv)
                    db.session.commit()
                    flash('تم تعديل البيع بنجاح', 'success')
            else:
                record = StorePurchase.query.get_or_404(record_id)
                if can_edit(current_user.role, record.date, record.created_by, current_user.id):
                    record.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
                    record.supplier_name = request.form.get('party_name')
                    record.supplier_phone = request.form.get('party_phone')
                    record.payment_type = request.form.get('payment_type', 'آجل')
                    for item in record.items:
                        inv = StoreInventory.query.filter_by(product_type=item.product_type,
                                                             product_size=item.product_size,
                                                             product_spec=item.product_spec).first()
                        if inv:
                            inv.current_quantity -= item.quantity
                        db.session.delete(item)
                    product_types = request.form.getlist('product_type')
                    product_sizes = request.form.getlist('product_size')
                    product_specs = request.form.getlist('product_spec')
                    quantities = request.form.getlist('quantity')
                    unit_prices = request.form.getlist('unit_price')
                    new_product_types = request.form.getlist('new_product_type')
                    new_product_sizes = request.form.getlist('new_product_size')
                    new_product_specs = request.form.getlist('new_product_spec')
                    for i in range(len(product_types)):
                        if not product_types[i].strip() or not quantities[i].strip():
                            continue
                        product_type = product_types[i]
                        if product_type == 'new':
                            product_type = new_product_types[i] if i < len(new_product_types) else ''
                            if product_type and not Category.query.filter_by(name=product_type).first():
                                db.session.add(Category(name=product_type))
                        product_size = product_sizes[i] if i < len(product_sizes) else ''
                        if product_size == 'new':
                            product_size = new_product_sizes[i] if i < len(new_product_sizes) else ''
                            if product_size and not Size.query.filter_by(value=product_size).first():
                                db.session.add(Size(value=product_size))
                        product_spec = product_specs[i] if i < len(product_specs) else ''
                        if product_spec == 'new':
                            product_spec = new_product_specs[i] if i < len(new_product_specs) else ''
                            if product_spec and not Thickness.query.filter_by(value=product_spec).first():
                                db.session.add(Thickness(value=product_spec))
                        item = StorePurchaseItem(
                            purchase_id=record.id,
                            product_type=product_type,
                            product_size=product_size,
                            product_spec=product_spec,
                            quantity=float(quantities[i]) if quantities[i] else 0,
                            unit_price=float(unit_prices[i]) if unit_prices[i] else 0,
                        )
                        item.total = item.quantity * item.unit_price
                        db.session.add(item)
                        inv = StoreInventory.query.filter_by(product_type=item.product_type,
                                                             product_size=item.product_size,
                                                             product_spec=item.product_spec).first()
                        if inv:
                            inv.current_quantity += item.quantity
                        else:
                            inv = StoreInventory(product_type=item.product_type,
                                                 product_size=item.product_size,
                                                 product_spec=item.product_spec,
                                                 current_quantity=item.quantity)
                            db.session.add(inv)
                    db.session.commit()
                    flash('تم تعديل الشراء بنجاح', 'success')
            return redirect(url_for('store_transactions'))

        transaction_type = request.form.get('transaction_type')
        record_date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        party_name = request.form.get('party_name')
        new_party_name = request.form.get('new_party_name', '').strip()
        if party_name == 'new' and new_party_name:
            party_name = new_party_name
        party_phone = request.form.get('party_phone')
        payment_type = request.form.get('payment_type', 'آجل')
        product_types = request.form.getlist('product_type')
        product_sizes = request.form.getlist('product_size')
        product_specs = request.form.getlist('product_spec')
        quantities = request.form.getlist('quantity')
        unit_prices = request.form.getlist('unit_price')
        new_product_types = request.form.getlist('new_product_type')
        new_product_sizes = request.form.getlist('new_product_size')
        new_product_specs = request.form.getlist('new_product_spec')
        has_items = False
        for i in range(len(product_types)):
            if product_types[i].strip() and quantities[i].strip():
                has_items = True
                break
        if not has_items:
            flash('⚠️ يجب إضافة على الأقل صنف واحد مع الكمية', 'danger')
            return redirect(url_for('store_transactions'))

        if transaction_type == 'sale':
            if party_name and not Customer.query.filter_by(name=party_name).first():
                db.session.add(Customer(name=party_name, phone=party_phone))
            new_sale = StoreSale(
                invoice_number=f"INV-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                customer_name=party_name,
                customer_phone=party_phone,
                payment_type=payment_type,
                date=record_date,
                created_by=current_user.id,
                created_at=datetime.utcnow()
            )
            db.session.add(new_sale)
            for i in range(len(product_types)):
                if not product_types[i].strip() or not quantities[i].strip():
                    continue
                product_type = product_types[i]
                if product_type == 'new':
                    product_type = new_product_types[i] if i < len(new_product_types) else ''
                    if product_type and not Category.query.filter_by(name=product_type).first():
                        db.session.add(Category(name=product_type))
                product_size = product_sizes[i] if i < len(product_sizes) else ''
                if product_size == 'new':
                    product_size = new_product_sizes[i] if i < len(new_product_sizes) else ''
                    if product_size and not Size.query.filter_by(value=product_size).first():
                        db.session.add(Size(value=product_size))
                product_spec = product_specs[i] if i < len(product_specs) else ''
                if product_spec == 'new':
                    product_spec = new_product_specs[i] if i < len(new_product_specs) else ''
                    if product_spec and not Thickness.query.filter_by(value=product_spec).first():
                        db.session.add(Thickness(value=product_spec))
                item = StoreSaleItem(
                    sale_id=new_sale.id,
                    product_type=product_type,
                    product_size=product_size,
                    product_spec=product_spec,
                    quantity=float(quantities[i]) if quantities[i] else 0,
                    unit_price=float(unit_prices[i]) if unit_prices[i] else 0,
                )
                item.total = item.quantity * item.unit_price
                db.session.add(item)
                inv = StoreInventory.query.filter_by(
                    product_type=item.product_type,
                    product_size=item.product_size,
                    product_spec=item.product_spec
                ).first()
                if inv:
                    inv.current_quantity -= item.quantity
                else:
                    inv = StoreInventory(
                        product_type=item.product_type,
                        product_size=item.product_size,
                        product_spec=item.product_spec,
                        current_quantity=-item.quantity
                    )
                    db.session.add(inv)
            db.session.commit()
            total = db.session.query(db.func.sum(StoreSaleItem.total)).filter(StoreSaleItem.sale_id == new_sale.id).scalar() or 0
            db.session.add(StoreDiary(
                date=record_date,
                description=f"بيع إلى {party_name} بقيمة {total}",
                amount=total,
                created_by=current_user.id,
                created_at=datetime.utcnow()
            ))
            db.session.commit()
            flash('تم تسجيل البيع بنجاح', 'success')
        else:
            if party_name and not Supplier.query.filter_by(name=party_name).first():
                db.session.add(Supplier(name=party_name, phone=party_phone))
            new_purchase = StorePurchase(
                invoice_number=f"PUR-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                supplier_name=party_name,
                supplier_phone=party_phone,
                payment_type=payment_type,
                date=record_date,
                created_by=current_user.id,
                created_at=datetime.utcnow()
            )
            db.session.add(new_purchase)
            for i in range(len(product_types)):
                if not product_types[i].strip() or not quantities[i].strip():
                    continue
                product_type = product_types[i]
                if product_type == 'new':
                    product_type = new_product_types[i] if i < len(new_product_types) else ''
                    if product_type and not Category.query.filter_by(name=product_type).first():
                        db.session.add(Category(name=product_type))
                product_size = product_sizes[i] if i < len(product_sizes) else ''
                if product_size == 'new':
                    product_size = new_product_sizes[i] if i < len(new_product_sizes) else ''
                    if product_size and not Size.query.filter_by(value=product_size).first():
                        db.session.add(Size(value=product_size))
                product_spec = product_specs[i] if i < len(product_specs) else ''
                if product_spec == 'new':
                    product_spec = new_product_specs[i] if i < len(new_product_specs) else ''
                    if product_spec and not Thickness.query.filter_by(value=product_spec).first():
                        db.session.add(Thickness(value=product_spec))
                item = StorePurchaseItem(
                    purchase_id=new_purchase.id,
                    product_type=product_type,
                    product_size=product_size,
                    product_spec=product_spec,
                    quantity=float(quantities[i]) if quantities[i] else 0,
                    unit_price=float(unit_prices[i]) if unit_prices[i] else 0,
                )
                item.total = item.quantity * item.unit_price
                db.session.add(item)
                inv = StoreInventory.query.filter_by(
                    product_type=item.product_type,
                    product_size=item.product_size,
                    product_spec=item.product_spec
                ).first()
                if inv:
                    inv.current_quantity += item.quantity
                else:
                    inv = StoreInventory(
                        product_type=item.product_type,
                        product_size=item.product_size,
                        product_spec=item.product_spec,
                        current_quantity=item.quantity
                    )
                    db.session.add(inv)
            db.session.commit()
            total = db.session.query(db.func.sum(StorePurchaseItem.total)).filter(StorePurchaseItem.purchase_id == new_purchase.id).scalar() or 0
            db.session.add(StoreDiary(
                date=record_date,
                description=f"شراء من {party_name} بقيمة {total}",
                amount=total,
                created_by=current_user.id,
                created_at=datetime.utcnow()
            ))
            db.session.commit()
            flash('تم تسجيل الشراء بنجاح', 'success')
        return redirect(url_for('store_transactions'))

    sales = StoreSale.query.order_by(StoreSale.date.asc(), StoreSale.id.asc()).all()
    purchases = StorePurchase.query.order_by(StorePurchase.date.asc(), StorePurchase.id.asc()).all()
    customers = Customer.query.order_by(Customer.name.asc()).all()
    suppliers = Supplier.query.order_by(Supplier.name.asc()).all()
    categories = Category.query.order_by(Category.name.asc()).all()
    sizes = Size.query.order_by(Size.value.asc()).all()
    thicknesses = Thickness.query.order_by(Thickness.value.asc()).all()
    return render_template('store/transactions.html',
                           sales=sales,
                           purchases=purchases,
                           customers=customers,
                           suppliers=suppliers,
                           categories=categories,
                           sizes=sizes,
                           thicknesses=thicknesses)

@app.route('/store/inventory', methods=['GET', 'POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab', 'ahmed', 'sayed')
def store_inventory():
    if request.method == 'POST':
        inventory_id = int(request.form.get('inventory_id'))
        item = StoreInventory.query.get_or_404(inventory_id)
        if request.form.get('delete'):
            if current_user.role in ['meg', 'admin', 'mariam', 'sayed']:
                db.session.delete(item)
                db.session.commit()
                flash('تم حذف عنصر المخزون', 'success')
        else:
            item.current_quantity = float(request.form.get('current_quantity', item.current_quantity))
            item.min_quantity = float(request.form.get('min_quantity', item.min_quantity))
            db.session.commit()
            flash('تم تحديث المخزون', 'success')
        return redirect(url_for('store_inventory'))
    inventory = StoreInventory.query.order_by(StoreInventory.product_type.asc(), StoreInventory.product_size.asc()).all()
    return render_template('store/inventory.html', inventory=inventory)

@app.route('/store/returns', methods=['GET', 'POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab', 'ahmed', 'sayed')
def store_returns():
    if request.method == 'POST':
        if request.form.get('delete_id'):
            record_id = int(request.form.get('delete_id'))
            record = StoreReturn.query.get_or_404(record_id)
            if can_delete_record(current_user.role, record.date):
                db.session.delete(record)
                db.session.commit()
                flash('تم حذف المرتجع بنجاح', 'success')
            return redirect(url_for('store_returns'))
        if request.form.get('edit_id'):
            record_id = int(request.form.get('edit_id'))
            record = StoreReturn.query.get_or_404(record_id)
            if can_edit(current_user.role, record.date, record.created_by, current_user.id):
                record.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
                record.return_type = request.form.get('return_type')
                record.party_name = request.form.get('party_name')
                record.product_type = request.form.get('product_type')
                record.product_size = request.form.get('product_size')
                record.product_spec = request.form.get('product_spec')
                record.quantity = float(request.form.get('quantity', 0))
                record.reason = request.form.get('reason')
                db.session.commit()
                flash('تم تحديث المرتجع بنجاح', 'success')
            return redirect(url_for('store_returns'))
        record_date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        return_type = request.form.get('return_type')
        party_name = request.form.get('party_name')
        product_type = request.form.get('product_type')
        product_size = request.form.get('product_size')
        product_spec = request.form.get('product_spec')
        quantity = float(request.form.get('quantity', 0))
        reason = request.form.get('reason')
        new_return = StoreReturn(date=record_date, return_type=return_type, party_name=party_name,
                                 product_type=product_type, product_size=product_size, product_spec=product_spec,
                                 quantity=quantity, reason=reason, created_by=current_user.id, created_at=datetime.utcnow())
        db.session.add(new_return)
        db.session.commit()
        flash('تم تسجيل المرتجع بنجاح', 'success')
        return redirect(url_for('store_returns'))
    returns = StoreReturn.query.order_by(StoreReturn.date.asc(), StoreReturn.id.asc()).all()
    return render_template('store/returns.html', returns=returns)

@app.route('/store/diary', methods=['GET', 'POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab', 'ahmed', 'sayed')
def store_diary():
    if request.method == 'POST':
        if request.form.get('delete_id'):
            record_id = int(request.form.get('delete_id'))
            record = StoreDiary.query.get_or_404(record_id)
            if can_delete_record(current_user.role, record.date):
                db.session.delete(record)
                db.session.commit()
                flash('تم حذف اليومية بنجاح', 'success')
            return redirect(url_for('store_diary'))
        if request.form.get('edit_id'):
            record_id = int(request.form.get('edit_id'))
            record = StoreDiary.query.get_or_404(record_id)
            if can_edit(current_user.role, record.date, record.created_by, current_user.id):
                record.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
                record.description = request.form.get('description')
                record.amount = float(request.form.get('amount', 0))
                db.session.commit()
                flash('تم تحديث اليومية بنجاح', 'success')
            return redirect(url_for('store_diary'))
        record_date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        description = request.form.get('description')
        amount = float(request.form.get('amount', 0))
        new_record = StoreDiary(date=record_date, description=description, amount=amount,
                                created_by=current_user.id, created_at=datetime.utcnow())
        db.session.add(new_record)
        db.session.commit()
        flash('تم تسجيل اليومية بنجاح', 'success')
        return redirect(url_for('store_diary'))
    diary = StoreDiary.query.order_by(StoreDiary.date.asc(), StoreDiary.id.asc()).all()
    return render_template('store/diary.html', diary=diary)

# ==================== الجرد (المخزون + الخزينة) ====================
@app.route('/inventory-audit', methods=['GET', 'POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'sayed')
def inventory_audit():
    if request.method == 'POST':
        if request.form.get('delete_id'):
            record_id = int(request.form.get('delete_id'))
            record = InventoryAudit.query.get_or_404(record_id)
            db.session.delete(record)
            db.session.commit()
            flash('تم حذف سجل الجرد بنجاح', 'success')
            return redirect(url_for('inventory_audit'))
        
        audit_date = datetime.strptime(request.form.get('audit_date'), '%Y-%m-%d').date()
        audit_type = request.form.get('audit_type')
        
        count = 0
        
        if audit_type == 'store':
            item_names = request.form.getlist('store_item_name[]')
            item_sizes = request.form.getlist('store_item_size[]')
            item_specs = request.form.getlist('store_item_spec[]')
            system_quantities = request.form.getlist('store_system_quantity[]')
            actual_quantities = request.form.getlist('store_actual_quantity[]')
            
            for i in range(len(item_names)):
                if not item_names[i].strip():
                    continue
                if not actual_quantities[i].strip():
                    continue
                
                item_name = item_names[i]
                item_size = item_sizes[i] if i < len(item_sizes) else ''
                item_spec = item_specs[i] if i < len(item_specs) else ''
                system_qty = float(system_quantities[i]) if system_quantities[i] else 0
                actual_qty = float(actual_quantities[i]) if actual_quantities[i] else 0
                difference = actual_qty - system_qty
                
                if difference < 0:
                    difference_type = 'ناقص'
                elif difference > 0:
                    difference_type = 'زيادة'
                else:
                    difference_type = 'متطابق'
                
                inv = StoreInventory.query.filter_by(
                    product_type=item_name,
                    product_size=item_size,
                    product_spec=item_spec
                ).first()
                if inv:
                    inv.current_quantity = actual_qty
                else:
                    inv = StoreInventory(
                        product_type=item_name,
                        product_size=item_size,
                        product_spec=item_spec,
                        current_quantity=actual_qty
                    )
                    db.session.add(inv)
                
                if difference != 0:
                    description = f"{difference_type} جرد: {item_name} {item_size} {item_spec} - {abs(difference)}"
                    db.session.add(StoreDiary(
                        date=audit_date,
                        description=description,
                        amount=0,
                        created_by=current_user.id,
                        created_at=datetime.utcnow()
                    ))
                
                new_record = InventoryAudit(
                    audit_date=audit_date, audit_type='store',
                    item_name=item_name, item_size=item_size, item_spec=item_spec,
                    system_quantity=system_qty, actual_quantity=actual_qty,
                    difference=difference, difference_type=difference_type,
                    created_by=current_user.id
                )
                db.session.add(new_record)
                count += 1
        
        elif audit_type == 'treasury':
            person_names = request.form.getlist('treasury_person_name[]')
            account_types = request.form.getlist('treasury_account_type[]')
            system_quantities = request.form.getlist('treasury_system_quantity[]')
            actual_quantities = request.form.getlist('treasury_actual_quantity[]')
            
            for i in range(len(person_names)):
                if not person_names[i].strip():
                    continue
                if not actual_quantities[i].strip():
                    continue
                
                person_name = person_names[i]
                account_type = account_types[i] if i < len(account_types) else ''
                system_qty = float(system_quantities[i]) if system_quantities[i] else 0
                actual_qty = float(actual_quantities[i]) if actual_quantities[i] else 0
                difference = actual_qty - system_qty
                
                if difference < 0:
                    difference_type = 'ناقص'
                elif difference > 0:
                    difference_type = 'زيادة'
                else:
                    difference_type = 'متطابق'
                
                account = TreasuryAccount.query.filter_by(
                    person_name=person_name,
                    account_type=account_type
                ).first()
                if account:
                    account.balance = actual_qty
                    if difference != 0:
                        txn_type = 'deposit' if difference > 0 else 'withdrawal'
                        db.session.add(TreasuryTransaction(
                            account_id=account.id,
                            transaction_type=txn_type,
                            amount=abs(difference),
                            source=f"{difference_type} جرد",
                            payment_method=account_type,
                            date=audit_date,
                            notes=f"{difference_type} جرد",
                            created_by=current_user.id,
                            created_at=datetime.utcnow()
                        ))
                
                new_record = InventoryAudit(
                    audit_date=audit_date, audit_type='treasury',
                    item_name=person_name, account_type=account_type,
                    system_quantity=system_qty, actual_quantity=actual_qty,
                    difference=difference, difference_type=difference_type,
                    created_by=current_user.id
                )
                db.session.add(new_record)
                count += 1
        
        db.session.commit()
        flash(f'✅ تم حفظ {count} عملية جرد بنجاح', 'success')
        return redirect(url_for('inventory_audit'))
    
    records = InventoryAudit.query.order_by(InventoryAudit.audit_date.desc()).all()
    inventory = StoreInventory.query.all()
    accounts = TreasuryAccount.query.all()
    categories = Category.query.order_by(Category.name.asc()).all()
    sizes = Size.query.order_by(Size.value.asc()).all()
    thicknesses = Thickness.query.order_by(Thickness.value.asc()).all()
    return render_template('inventory_audit.html',
                           records=records, inventory=inventory, accounts=accounts,
                           categories=categories, sizes=sizes, thicknesses=thicknesses)


# ==================== Routes للإضافة السريعة ====================
@app.route('/add-quick-category', methods=['POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'sayed')
def add_quick_category():
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'اسم فارغ'})
    
    existing = Category.query.filter_by(name=name).first()
    if existing:
        return jsonify({'success': True, 'id': existing.id})
    
    new_cat = Category(name=name)
    db.session.add(new_cat)
    db.session.commit()
    return jsonify({'success': True, 'id': new_cat.id})


@app.route('/add-quick-size', methods=['POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'sayed')
def add_quick_size():
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'اسم فارغ'})
    
    existing = Size.query.filter_by(value=name).first()
    if existing:
        return jsonify({'success': True, 'id': existing.id})
    
    new_size = Size(value=name)
    db.session.add(new_size)
    db.session.commit()
    return jsonify({'success': True, 'id': new_size.id})


@app.route('/add-quick-thickness', methods=['POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'sayed')
def add_quick_thickness():
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'اسم فارغ'})
    
    existing = Thickness.query.filter_by(value=name).first()
    if existing:
        return jsonify({'success': True, 'id': existing.id})
    
    new_thickness = Thickness(value=name)
    db.session.add(new_thickness)
    db.session.commit()
    return jsonify({'success': True, 'id': new_thickness.id})


@app.route('/add-quick-account', methods=['POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'sayed')
def add_quick_account():
    data = request.get_json()
    person_name = data.get('person_name', '').strip()
    account_type = data.get('account_type', '').strip()
    
    if not person_name or not account_type:
        return jsonify({'success': False, 'error': 'بيانات ناقصة'})
    
    existing = TreasuryAccount.query.filter_by(
        person_name=person_name,
        account_type=account_type
    ).first()
    
    if existing:
        return jsonify({'success': True, 'id': existing.id})
    
    new_account = TreasuryAccount(
        person_name=person_name,
        account_type=account_type,
        balance=0
    )
    db.session.add(new_account)
    db.session.commit()
    return jsonify({'success': True, 'id': new_account.id})


@app.route('/add-quick-party', methods=['POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab', 'ahmed', 'sayed')
def add_quick_party():
    data = request.get_json()
    party_type = data.get('party_type', 'customer')
    name = data.get('name', '').strip()
    phone = data.get('phone', '').strip()
    
    if not name:
        return jsonify({'success': False, 'error': 'اسم فارغ'})
    
    if party_type == 'customer':
        existing = Customer.query.filter_by(name=name).first()
        if existing:
            return jsonify({'success': True, 'id': existing.id})
        new_party = Customer(name=name, phone=phone)
    else:
        existing = Supplier.query.filter_by(name=name).first()
        if existing:
            return jsonify({'success': True, 'id': existing.id})
        new_party = Supplier(name=name, phone=phone)
    
    db.session.add(new_party)
    db.session.commit()
    return jsonify({'success': True, 'id': new_party.id})


# ==================== تصدير Excel ====================
@app.route('/inventory-audit/export')
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'sayed')
def inventory_audit_export():
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    
    from_date_str = request.args.get('from_date')
    to_date_str = request.args.get('to_date')
    
    query = InventoryAudit.query
    if from_date_str:
        query = query.filter(InventoryAudit.audit_date >= datetime.strptime(from_date_str, '%Y-%m-%d').date())
    if to_date_str:
        query = query.filter(InventoryAudit.audit_date <= datetime.strptime(to_date_str, '%Y-%m-%d').date())
    
    records = query.order_by(InventoryAudit.audit_date.desc()).all()
    
    wb = Workbook()
    ws = wb.active
    ws.title = "الجرد"
    ws.sheet_view.rightToLeft = True
    
    headers = ['التاريخ', 'النوع', 'الصنف/الحساب', 'المقاس', 'المواصفات', 'المسجل', 'الفعلي', 'الفرق', 'الحالة']
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill(start_color='7C3AED', end_color='7C3AED', fill_type='solid')
        cell.alignment = Alignment(horizontal='center')
    
    for r in records:
        ws.append([
            r.audit_date.strftime('%Y-%m-%d'),
            'مخزون' if r.audit_type == 'store' else 'خزينة',
            r.item_name or '-',
            r.item_size or '-',
            r.item_spec or '-',
            r.system_quantity,
            r.actual_quantity,
            r.difference,
            r.difference_type
        ])
    
    from io import BytesIO
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    
    return send_file(output, as_attachment=True,
                     download_name=f'audit_{datetime.now().strftime("%Y%m%d")}.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


# ==================== التقرير الشهري ====================
@app.route('/inventory-audit/monthly')
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'sayed')
def inventory_audit_monthly():
    month = request.args.get('month', datetime.now().strftime('%Y-%m'))
    year, mon = month.split('-')
    
    from_date = date(int(year), int(mon), 1)
    if int(mon) == 12:
        to_date = date(int(year) + 1, 1, 1)
    else:
        to_date = date(int(year), int(mon) + 1, 1)
    
    records = InventoryAudit.query.filter(
        InventoryAudit.audit_date >= from_date,
        InventoryAudit.audit_date < to_date
    ).order_by(InventoryAudit.audit_date.desc()).all()
    
    total_shortage = sum(abs(r.difference) for r in records if r.difference < 0)
    total_surplus = sum(r.difference for r in records if r.difference > 0)
    
    return render_template('inventory_audit_monthly.html',
                           records=records, month=month,
                           total_shortage=total_shortage,
                           total_surplus=total_surplus)

# ==================== الخزينة ====================
@app.route('/treasury')
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'ahmed', 'eid', 'abdo', 'sayed')
def treasury_index():
    if current_user.role in ['meg', 'admin', 'mariam', 'sayed']:
        persons = ['الحاج أحمد', 'عيد', 'عبدالله', 'الحاج فتحي']
        for person in persons:
            for acc_type in ['كاش', 'فودافون كاش', 'انستا باي', 'شيك']:
                get_or_create_treasury_account(person, acc_type)
    else:
        person_name = current_user.full_name
        for acc_type in ['كاش', 'فودافون كاش', 'انستا باي', 'شيك']:
            get_or_create_treasury_account(person_name, acc_type)
    accounts = get_visible_accounts_for_current_user()
    if current_user.role in ['meg', 'admin', 'mariam', 'sayed']:
        transactions = TreasuryTransaction.query.order_by(TreasuryTransaction.date.asc(), TreasuryTransaction.id.asc()).limit(50).all()
    else:
        transactions = TreasuryTransaction.query.filter_by(created_by=current_user.id).order_by(TreasuryTransaction.date.asc(), TreasuryTransaction.id.asc()).limit(50).all()
    return render_template('treasury/index.html', accounts=accounts, transactions=transactions)

@app.route('/treasury/transactions', methods=['GET', 'POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'ahmed', 'eid', 'abdo', 'sayed')
def treasury_transactions():
    if current_user.role in ['meg', 'admin', 'mariam', 'sayed']:
        persons = ['الحاج أحمد', 'عيد', 'عبدالله', 'الحاج فتحي']
        for person in persons:
            for acc_type in ['كاش', 'فودافون كاش', 'انستا باي', 'شيك']:
                get_or_create_treasury_account(person, acc_type)
    else:
        person_name = current_user.full_name
        for acc_type in ['كاش', 'فودافون كاش', 'انستا باي', 'شيك']:
            get_or_create_treasury_account(person_name, acc_type)
    if request.method == 'POST':
        if request.form.get('delete_id'):
            record_id = int(request.form.get('delete_id'))
            record = TreasuryTransaction.query.get_or_404(record_id)
            if current_user.role in ['meg', 'admin', 'mariam', 'sayed']:
                account = TreasuryAccount.query.get(record.account_id)
                if account:
                    if record.transaction_type == 'deposit':
                        account.balance -= record.amount
                    else:
                        account.balance += record.amount
                db.session.delete(record)
                db.session.commit()
                flash('تم حذف الحركة بنجاح', 'success')
            return redirect(url_for('treasury_transactions'))
        if request.form.get('edit_id'):
            record_id = int(request.form.get('edit_id'))
            record = TreasuryTransaction.query.get_or_404(record_id)
            if can_edit(current_user.role, record.date, record.created_by, current_user.id):
                old_account = TreasuryAccount.query.get(record.account_id)
                if old_account:
                    if record.transaction_type == 'deposit':
                        old_account.balance -= record.amount
                    else:
                        old_account.balance += record.amount
                record.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
                new_account_id = int(request.form.get('account_id'))
                record.transaction_type = request.form.get('transaction_type')
                record.amount = float(request.form.get('amount', 0))
                record.source = request.form.get('source')
                record.payment_method = request.form.get('payment_method')
                record.notes = request.form.get('notes')
                record.account_id = new_account_id
                new_account = TreasuryAccount.query.get(new_account_id)
                if new_account:
                    if record.transaction_type == 'deposit':
                        new_account.balance += record.amount
                    else:
                        new_account.balance -= record.amount
                db.session.commit()
                flash('تم تحديث الحركة بنجاح', 'success')
            return redirect(url_for('treasury_transactions'))
        record_date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        account_id = int(request.form.get('account_id'))
        transaction_type = request.form.get('transaction_type')
        amount = float(request.form.get('amount', 0))
        source = request.form.get('source')
        payment_method = request.form.get('payment_method')
        notes = request.form.get('notes')
        account = TreasuryAccount.query.get(account_id)
        if account:
            if transaction_type == 'deposit':
                account.balance += amount
            elif transaction_type == 'withdrawal':
                account.balance -= amount
        new_transaction = TreasuryTransaction(
            account_id=account_id,
            transaction_type=transaction_type,
            amount=amount,
            source=source,
            payment_method=payment_method,
            date=record_date,
            notes=notes,
            created_by=current_user.id,
            created_at=datetime.utcnow()
        )
        db.session.add(new_transaction)
        db.session.commit()
        flash('تم تسجيل الحركة بنجاح', 'success')
        return redirect(url_for('treasury_transactions'))
    accounts = get_visible_accounts_for_current_user()
    if current_user.role in ['meg', 'admin', 'mariam', 'sayed']:
        transactions = TreasuryTransaction.query.order_by(TreasuryTransaction.date.asc(), TreasuryTransaction.id.asc()).all()
    else:
        transactions = TreasuryTransaction.query.filter_by(created_by=current_user.id).order_by(TreasuryTransaction.date.asc(), TreasuryTransaction.id.asc()).all()
    customers = Customer.query.order_by(Customer.name.asc()).all()
    suppliers = Supplier.query.order_by(Supplier.name.asc()).all()
    return render_template('treasury/transactions.html',
                           accounts=accounts,
                           transactions=transactions,
                           customers=customers,
                           suppliers=suppliers)

@app.route('/treasury/transfers', methods=['GET', 'POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'sayed')
def treasury_transfers():
    if request.method == 'POST':
        if request.form.get('delete_id'):
            record_id = int(request.form.get('delete_id'))
            record = TreasuryTransfer.query.get_or_404(record_id)
            if current_user.role in ['meg', 'admin', 'mariam', 'sayed']:
                db.session.delete(record)
                db.session.commit()
                flash('تم حذف التحويل بنجاح', 'success')
            return redirect(url_for('treasury_transfers'))
        if request.form.get('edit_id'):
            record_id = int(request.form.get('edit_id'))
            record = TreasuryTransfer.query.get_or_404(record_id)
            if current_user.role in ['meg', 'admin', 'mariam', 'sayed']:
                record.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
                record.from_person = request.form.get('from_person')
                record.to_person = request.form.get('to_person')
                record.amount = float(request.form.get('amount', 0))
                record.payment_method = request.form.get('payment_method')
                record.notes = request.form.get('notes')
                db.session.commit()
                flash('تم تحديث التحويل بنجاح', 'success')
            return redirect(url_for('treasury_transfers'))
        date_str = request.form.get('date')
        from_person = request.form.get('from_person')
        payment_method = request.form.get('payment_method')
        notes = request.form.get('notes')
        to_persons = request.form.getlist('to_person[]')
        amounts = request.form.getlist('amount[]')
        for i in range(len(to_persons)):
            if to_persons[i].strip() and amounts[i].strip():
                transfer = TreasuryTransfer(
                    date=datetime.strptime(date_str, '%Y-%m-%d').date(),
                    from_person=from_person,
                    to_person=to_persons[i],
                    amount=float(amounts[i]),
                    payment_method=payment_method,
                    notes=notes,
                    created_by=current_user.id,
                    created_at=datetime.utcnow()
                )
                db.session.add(transfer)
        db.session.commit()
        flash('تم تسجيل التحويلات بنجاح', 'success')
        return redirect(url_for('treasury_transfers'))
    transfers = TreasuryTransfer.query.order_by(TreasuryTransfer.date.asc(), TreasuryTransfer.id.asc()).all()
    return render_template('treasury/transfers.html', transfers=transfers)

@app.route('/treasury/accounts', methods=['GET', 'POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'sayed')
def treasury_accounts():
    if request.method == 'POST':
        if request.form.get('delete_id'):
            account_id = int(request.form.get('delete_id'))
            account = TreasuryAccount.query.get_or_404(account_id)
            if current_user.role in ['meg', 'admin', 'mariam', 'sayed']:
                if account.transactions:
                    flash('لا يمكن حذف حساب له معاملات', 'danger')
                else:
                    db.session.delete(account)
                    db.session.commit()
                    flash('تم حذف الحساب', 'success')
            return redirect(url_for('treasury_accounts'))
        if request.form.get('edit_id'):
            account_id = int(request.form.get('edit_id'))
            account = TreasuryAccount.query.get_or_404(account_id)
            if current_user.role in ['meg', 'admin', 'mariam', 'sayed']:
                account.person_name = request.form.get('person_name')
                account.account_type = request.form.get('account_type')
                account.balance = float(request.form.get('balance', 0))
                db.session.commit()
                flash('تم تحديث الحساب', 'success')
            return redirect(url_for('treasury_accounts'))
        person_name = request.form.get('person_name')
        account_type = request.form.get('account_type')
        balance = float(request.form.get('balance', 0))
        new_account = TreasuryAccount(person_name=person_name, account_type=account_type, balance=balance)
        db.session.add(new_account)
        db.session.commit()
        flash('تم إضافة الحساب', 'success')
        return redirect(url_for('treasury_accounts'))
    accounts = TreasuryAccount.query.order_by(TreasuryAccount.person_name.asc(), TreasuryAccount.account_type.asc()).all()
    return render_template('treasury/accounts.html', accounts=accounts)

@app.route('/financial-transactions', methods=['GET', 'POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab', 'ahmed', 'eid', 'abdo', 'sayed')
def financial_transactions():
    if request.method == 'POST':
        dates = request.form.getlist('date[]')
        types = request.form.getlist('transaction_type[]')
        amounts = request.form.getlist('amount[]')
        payment_methods = request.form.getlist('payment_method[]')
        notes_list = request.form.getlist('notes[]')
        from_parties = request.form.getlist('from_party[]')
        to_parties = request.form.getlist('to_party[]')
        new_from_parties = request.form.getlist('new_from_party[]')
        new_to_parties = request.form.getlist('new_to_party[]')
        for i in range(len(amounts)):
            if not amounts[i].strip():
                continue
            try:
                amount = float(amounts[i])
                record_date = datetime.strptime(dates[i], '%Y-%m-%d').date() if dates[i] else date.today()
                txn_type = types[i] if i < len(types) else 'deposit'
                payment_method = payment_methods[i] if i < len(payment_methods) else 'كاش'
                notes = notes_list[i] if i < len(notes_list) else ''
                from_party = from_parties[i] if i < len(from_parties) else ''
                to_party = to_parties[i] if i < len(to_parties) else ''
                new_from_party = new_from_parties[i] if i < len(new_from_parties) else ''
                new_to_party = new_to_parties[i] if i < len(new_to_parties) else ''
                if from_party == 'new' and new_from_party:
                    if txn_type == 'deposit':
                        if not Customer.query.filter_by(name=new_from_party).first():
                            db.session.add(Customer(name=new_from_party))
                    from_party = new_from_party
                elif from_party and from_party not in ['', 'new']:
                    if txn_type == 'deposit':
                        if not Customer.query.filter_by(name=from_party).first() and not Supplier.query.filter_by(name=from_party).first():
                            db.session.add(Customer(name=from_party))
                if to_party == 'new' and new_to_party:
                    if txn_type == 'withdrawal':
                        if not Supplier.query.filter_by(name=new_to_party).first():
                            db.session.add(Supplier(name=new_to_party))
                    to_party = new_to_party
                elif to_party and to_party not in ['', 'new']:
                    if txn_type == 'withdrawal':
                        if not Supplier.query.filter_by(name=to_party).first() and not Customer.query.filter_by(name=to_party).first():
                            db.session.add(Supplier(name=to_party))
                account = None
                if txn_type == 'deposit':
                    account_name = current_user.full_name
                    account = TreasuryAccount.query.filter_by(person_name=account_name, account_type=payment_method).first()
                    if not account:
                        account = TreasuryAccount(person_name=account_name, account_type=payment_method, balance=0)
                        db.session.add(account)
                    account.balance += amount
                    source = from_party
                    txn_type_db = 'deposit'
                elif txn_type == 'withdrawal':
                    account_name = current_user.full_name
                    account = TreasuryAccount.query.filter_by(person_name=account_name, account_type=payment_method).first()
                    if not account:
                        account = TreasuryAccount(person_name=account_name, account_type=payment_method, balance=0)
                        db.session.add(account)
                    account.balance -= amount
                    source = to_party
                    txn_type_db = 'withdrawal'
                elif txn_type == 'transfer_customer_supplier':
                    account = TreasuryAccount.query.filter_by(person_name='تحويلات العملاء', account_type='تحويل').first()
                    if not account:
                        account = TreasuryAccount(person_name='تحويلات العملاء', account_type='تحويل', balance=0)
                        db.session.add(account)
                    source = f"من {from_party} إلى {to_party}"
                    txn_type_db = 'transfer'
                new_txn = TreasuryTransaction(
                    account_id=account.id,
                    transaction_type=txn_type_db,
                    amount=amount,
                    source=source,
                    payment_method=payment_method,
                    date=record_date,
                    notes=notes,
                    created_by=current_user.id,
                    created_at=datetime.utcnow()
                )
                db.session.add(new_txn)
            except Exception as e:
                print(f"❌ Error: {e}")
                continue
        db.session.commit()
        flash('✅ تم تسجيل المعاملات المالية بنجاح', 'success')
        return redirect(url_for('financial_transactions'))
    transactions = TreasuryTransaction.query.order_by(TreasuryTransaction.date.asc(), TreasuryTransaction.id.asc()).all()
    accounts = TreasuryAccount.query.all()
    customers = Customer.query.order_by(Customer.name.asc()).all()
    suppliers = Supplier.query.order_by(Supplier.name.asc()).all()
    return render_template('reports/financial.html',
                           transactions=transactions,
                           accounts=accounts,
                           customers=customers,
                           suppliers=suppliers)

# ==================== التقارير ====================
@app.route('/reports')
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab', 'sayed')
def reports_index():
    return render_template('reports/index.html')

@app.route('/reports/custom')
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab', 'sayed')
def reports_custom():
    from_date_str = request.args.get('from_date')
    to_date_str = request.args.get('to_date')
    report_type = request.args.get('report_type', 'all')
    if not from_date_str or not to_date_str:
        return render_template('reports/custom.html',
                               from_date=None, to_date=None, report_type=report_type,
                               combined_diary=[], raw_materials=[], production=[],
                               sales=[], purchases=[], transactions=[])
    from_date = datetime.strptime(from_date_str, '%Y-%m-%d').date()
    to_date = datetime.strptime(to_date_str, '%Y-%m-%d').date()
    raw_materials = FactoryRawMaterial.query.filter(FactoryRawMaterial.date >= from_date, FactoryRawMaterial.date <= to_date).order_by(FactoryRawMaterial.date.asc()).all()
    production = FactoryProduction.query.filter(FactoryProduction.date >= from_date, FactoryProduction.date <= to_date).order_by(FactoryProduction.date.asc()).all()
    factory_diary = FactoryDiary.query.filter(FactoryDiary.date >= from_date, FactoryDiary.date <= to_date).order_by(FactoryDiary.date.asc()).all()
    sales = StoreSale.query.filter(StoreSale.date >= from_date, StoreSale.date <= to_date).order_by(StoreSale.date.asc()).all()
    purchases = StorePurchase.query.filter(StorePurchase.date >= from_date, StorePurchase.date <= to_date).order_by(StorePurchase.date.asc()).all()
    store_diary = StoreDiary.query.filter(StoreDiary.date >= from_date, StoreDiary.date <= to_date).order_by(StoreDiary.date.asc()).all()
    transactions = TreasuryTransaction.query.filter(TreasuryTransaction.date >= from_date, TreasuryTransaction.date <= to_date).order_by(TreasuryTransaction.date.asc()).all()
    combined_diary = []
    for d in factory_diary:
        combined_diary.append({'date': d.date, 'type': 'مصنع', 'description': d.description, 'amount': d.amount, 'created_by': d.created_by})
    for d in store_diary:
        combined_diary.append({'date': d.date, 'type': 'محل', 'description': d.description, 'amount': d.amount, 'created_by': d.created_by})
    combined_diary.sort(key=lambda x: x['date'])
    return render_template('reports/custom.html',
                           from_date=from_date_str, to_date=to_date_str, report_type=report_type,
                           raw_materials=raw_materials, production=production, factory_diary=factory_diary,
                           sales=sales, purchases=purchases, transactions=transactions,
                           combined_diary=combined_diary)

@app.route('/reports/customers')
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab', 'sayed')
def reports_customers():
    customers = Customer.query.order_by(Customer.name.asc()).all()
    customers_data = []
    for c in customers:
        sales = StoreSale.query.filter_by(customer_name=c.name).all()
        total_purchases = sum(s.total for s in sales)
        total_paid = sum(s.paid_amount for s in sales)
        customers_data.append({
            'customer': c,
            'total_purchases': total_purchases,
            'total_paid': total_paid,
            'remaining': total_purchases - total_paid
        })
    return render_template('reports/customers.html', customers_data=customers_data)

@app.route('/reports/customers/<int:customer_id>')
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab', 'sayed')
def report_single_customer(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    sales = StoreSale.query.filter_by(customer_name=customer.name).order_by(StoreSale.date.asc(), StoreSale.id.asc()).all()
    total_purchases = sum(s.total for s in sales)
    total_paid = sum(s.paid_amount for s in sales)
    total_remaining = total_purchases - total_paid
    treasury_txns = TreasuryTransaction.query.filter_by(source=customer.name).order_by(TreasuryTransaction.date.asc()).all()
    return render_template('reports/customer_detail.html',
                           customer=customer, sales=sales,
                           total_purchases=total_purchases, total_paid=total_paid,
                           total_remaining=total_remaining, treasury_txns=treasury_txns)

@app.route('/reports/suppliers')
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab', 'sayed')
def reports_suppliers():
    suppliers = Supplier.query.order_by(Supplier.name.asc()).all()
    suppliers_data = []
    for s in suppliers:
        purchases = StorePurchase.query.filter_by(supplier_name=s.name).all()
        total_purchases = sum(p.total for p in purchases)
        total_paid = sum(p.paid_amount for p in purchases)
        suppliers_data.append({
            'supplier': s,
            'total_purchases': total_purchases,
            'total_paid': total_paid,
            'remaining': total_purchases - total_paid
        })
    return render_template('reports/suppliers.html', suppliers_data=suppliers_data)

@app.route('/reports/suppliers/<int:supplier_id>')
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab', 'sayed')
def report_single_supplier(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)
    purchases = StorePurchase.query.filter_by(supplier_name=supplier.name).order_by(StorePurchase.date.asc(), StorePurchase.id.asc()).all()
    total_purchases = sum(p.total for p in purchases)
    total_paid = sum(p.paid_amount for p in purchases)
    total_remaining = total_purchases - total_paid
    treasury_txns = TreasuryTransaction.query.filter_by(source=supplier.name).order_by(TreasuryTransaction.date.asc()).all()
    return render_template('reports/supplier_detail.html',
                           supplier=supplier, purchases=purchases,
                           total_purchases=total_purchases, total_paid=total_paid,
                           total_remaining=total_remaining, treasury_txns=treasury_txns)

# ==================== الإدارة ====================
@app.route('/admin/users')
@custom_login_required
@role_required('meg', 'admin', 'sayed')
def admin_users():
    users = User.query.filter_by(is_hidden=False).all() if current_user.role != 'meg' else User.query.all()
    return render_template('admin/users.html', users=users)

@app.route('/admin/users/add', methods=['GET', 'POST'])
@custom_login_required
@role_required('meg', 'admin', 'sayed')
def admin_add_user():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        full_name = request.form.get('full_name')
        role = request.form.get('role')
        phone = request.form.get('phone')
        existing = User.query.filter_by(username=username).first()
        if existing:
            flash('اسم المستخدم موجود بالفعل', 'danger')
            return redirect(url_for('admin_add_user'))
        new_user = User(username=username, full_name=full_name, role=role, phone=phone,
                        is_hidden=False, created_by=current_user.id, created_at=datetime.utcnow())
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        flash('تم إضافة المستخدم بنجاح', 'success')
        return redirect(url_for('admin_users'))
    return render_template('admin/add_user.html')

@app.route('/admin/users/<int:user_id>/edit', methods=['GET', 'POST'])
@custom_login_required
@role_required('meg', 'admin', 'sayed')
def admin_edit_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.role == 'meg' and current_user.role != 'meg':
        flash('غير مصرح لك بتعديل هذا المستخدم', 'danger')
        return redirect(url_for('admin_users'))
    if request.method == 'POST':
        user.full_name = request.form.get('full_name')
        user.role = request.form.get('role')
        user.phone = request.form.get('phone')
        new_password = request.form.get('password')
        if new_password:
            user.set_password(new_password)
        db.session.commit()
        flash('تم تحديث بيانات المستخدم بنجاح', 'success')
        return redirect(url_for('admin_users'))
    return render_template('admin/edit_user.html', user=user)

@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@custom_login_required
@role_required('meg', 'admin')
def admin_delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.role == 'meg':
        flash('لا يمكن حذف حساب MEG', 'danger')
        return redirect(url_for('admin_users'))
    db.session.delete(user)
    db.session.commit()
    flash('تم حذف المستخدم بنجاح', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/activity')
@custom_login_required
@role_required('meg', 'admin', 'sayed')
def admin_activity():
    activities = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).limit(200).all()
    inactive_users = []
    threshold = datetime.utcnow() - timedelta(days=3)
    all_users = User.query.filter_by(is_hidden=False).all()
    for user in all_users:
        if user.last_activity and user.last_activity < threshold:
            inactive_users.append(user)
    return render_template('admin/activity.html', activities=activities, inactive_users=inactive_users)

@app.route('/admin/categories')
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'sayed')
def admin_categories():
    categories = Category.query.all()
    sizes = Size.query.all()
    thicknesses = Thickness.query.all()
    suppliers = Supplier.query.all()
    customers = Customer.query.all()
    return render_template('admin/categories.html',
                           categories=categories, sizes=sizes, thicknesses=thicknesses,
                           suppliers=suppliers, customers=customers)

@app.route('/admin/categories/add', methods=['POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'sayed')
def admin_add_category():
    category_type = request.form.get('category_type')
    name = request.form.get('name')
    if category_type == 'category':
        if not Category.query.filter_by(name=name).first():
            db.session.add(Category(name=name))
    elif category_type == 'size':
        if not Size.query.filter_by(value=name).first():
            db.session.add(Size(value=name))
    elif category_type == 'thickness':
        if not Thickness.query.filter_by(value=name).first():
            db.session.add(Thickness(value=name))
    elif category_type == 'supplier':
        if not Supplier.query.filter_by(name=name).first():
            db.session.add(Supplier(name=name))
    elif category_type == 'customer':
        if not Customer.query.filter_by(name=name).first():
            db.session.add(Customer(name=name))
    db.session.commit()
    flash('تمت الإضافة بنجاح', 'success')
    return redirect(url_for('admin_categories'))

@app.route('/admin/categories/<string:category_type>/<int:item_id>/edit', methods=['POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'sayed')
def admin_edit_category(category_type, item_id):
    new_name = request.form.get('name')
    if category_type == 'category':
        item = Category.query.get_or_404(item_id)
        item.name = new_name
    elif category_type == 'size':
        item = Size.query.get_or_404(item_id)
        item.value = new_name
    elif category_type == 'thickness':
        item = Thickness.query.get_or_404(item_id)
        item.value = new_name
    elif category_type == 'supplier':
        item = Supplier.query.get_or_404(item_id)
        item.name = new_name
        item.phone = request.form.get('phone', item.phone)
    elif category_type == 'customer':
        item = Customer.query.get_or_404(item_id)
        item.name = new_name
        item.phone = request.form.get('phone', item.phone)
    db.session.commit()
    flash('تم التعديل بنجاح', 'success')
    return redirect(url_for('admin_categories'))

@app.route('/admin/categories/<string:category_type>/<int:item_id>/delete', methods=['POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'sayed')
def admin_delete_category(category_type, item_id):
    if category_type == 'category':
        item = Category.query.get_or_404(item_id)
        db.session.delete(item)
    elif category_type == 'size':
        item = Size.query.get_or_404(item_id)
        db.session.delete(item)
    elif category_type == 'thickness':
        item = Thickness.query.get_or_404(item_id)
        db.session.delete(item)
    elif category_type == 'supplier':
        item = Supplier.query.get_or_404(item_id)
        db.session.delete(item)
    elif category_type == 'customer':
        item = Customer.query.get_or_404(item_id)
        db.session.delete(item)
    db.session.commit()
    flash('تم الحذف بنجاح', 'success')
    return redirect(url_for('admin_categories'))

# ==================== الإعدادات ====================
@app.route('/settings/profile', methods=['GET', 'POST'])
@custom_login_required
def settings_profile():
    if request.method == 'POST':
        current_user.full_name = request.form.get('full_name')
        current_user.phone = request.form.get('phone')
        db.session.commit()
        flash('تم تحديث الملف الشخصي بنجاح', 'success')
        return redirect(url_for('settings_profile'))
    return render_template('settings/profile.html')

@app.route('/settings/password', methods=['GET', 'POST'])
@custom_login_required
def settings_password():
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        if not current_user.check_password(current_password):
            flash('كلمة المرور الحالية غير صحيحة', 'danger')
            return redirect(url_for('settings_password'))
        if new_password != confirm_password:
            flash('كلمة المرور الجديدة غير متطابقة', 'danger')
            return redirect(url_for('settings_password'))
        if len(new_password) < 6:
            flash('كلمة المرور يجب ألا تقل عن 6 أحرف', 'danger')
            return redirect(url_for('settings_password'))
        current_user.set_password(new_password)
        db.session.commit()
        flash('تم تغيير كلمة المرور بنجاح', 'success')
        return redirect(url_for('dashboard'))
    return render_template('settings/password.html')

# ====================================================================
# ==================== شركة الماسة ====================
# ====================================================================

@app.route('/almasa')
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_index():
    partnership_cranes = AlMasaCrane.query.filter_by(crane_type='partnership').order_by(AlMasaCrane.id.asc()).all()
    private_cranes = AlMasaPrivateCrane.query.order_by(AlMasaPrivateCrane.id.asc()).all()
    supplies = AlMasaSupply.query.order_by(AlMasaSupply.id.asc()).all()
    return render_template('almasa/index.html',
                           partnership_cranes=partnership_cranes,
                           private_cranes=private_cranes,
                           supplies=supplies)

@app.route('/almasa/cranes', methods=['GET', 'POST'])
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_cranes():
    if request.method == 'POST':
        name = request.form.get('name')
        notes = request.form.get('notes')
        partner_names = request.form.getlist('partner_name[]')
        partner_percentages = request.form.getlist('partner_percentage[]')
        is_basic = request.form.getlist('is_basic[]')
        new_crane = AlMasaCrane(name=name, notes=notes, crane_type='partnership')
        db.session.add(new_crane)
        db.session.flush()
        for i in range(len(partner_names)):
            if partner_names[i].strip():
                partner = AlMasaPartner(
                    crane_id=new_crane.id,
                    name=partner_names[i],
                    percentage=float(partner_percentages[i]) if partner_percentages[i] else 0,
                    is_basic=True if i < len(is_basic) and is_basic[i] == '1' else False
                )
                db.session.add(partner)
        db.session.commit()
        flash('تم إضافة الونش بنجاح', 'success')
        return redirect(url_for('almasa_cranes'))
    cranes = AlMasaCrane.query.filter_by(crane_type='partnership').order_by(AlMasaCrane.id.asc()).all()
    return render_template('almasa/cranes.html', cranes=cranes)

@app.route('/almasa/cranes/<int:crane_id>')
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_crane_detail(crane_id):
    crane = AlMasaCrane.query.get_or_404(crane_id)
    operations = AlMasaOperation.query.filter_by(crane_id=crane_id).order_by(AlMasaOperation.start_date.asc()).all()
    checks = AlMasaCheck.query.filter_by(crane_id=crane_id).order_by(AlMasaCheck.due_date.asc()).all()
    expenses = AlMasaExpense.query.filter_by(crane_id=crane_id).order_by(AlMasaExpense.date.asc()).all()
    partners = AlMasaPartner.query.filter_by(crane_id=crane_id).all()
    return render_template('almasa/crane_detail.html',
                           crane=crane, operations=operations, checks=checks,
                           expenses=expenses, partners=partners)

@app.route('/almasa/cranes/<int:crane_id>/delete', methods=['POST'])
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_crane_delete(crane_id):
    crane = AlMasaCrane.query.get_or_404(crane_id)
    db.session.delete(crane)
    db.session.commit()
    flash('تم حذف الونش بنجاح', 'success')
    return redirect(url_for('almasa_cranes'))

@app.route('/almasa/operations/add', methods=['POST'])
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_add_operation():
    crane_id = int(request.form.get('crane_id'))
    start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
    end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date() if request.form.get('end_date') else None
    actual_daily = float(request.form.get('actual_daily_value', 0))
    default_daily = float(request.form.get('default_daily_value', 0))
    days_count = int(request.form.get('days_count', 0))
    actual_total = actual_daily * days_count
    default_total = default_daily * days_count
    operation = AlMasaOperation(
        crane_id=crane_id, start_date=start_date, end_date=end_date,
        actual_daily_value=actual_daily, default_daily_value=default_daily,
        days_count=days_count, actual_total=actual_total, default_total=default_total,
        created_by=current_user.id
    )
    db.session.add(operation)
    db.session.commit()
    flash('تم إضافة العملية بنجاح', 'success')
    return redirect(url_for('almasa_crane_detail', crane_id=crane_id))

@app.route('/almasa/operations/<int:op_id>/delete', methods=['POST'])
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_operation_delete(op_id):
    operation = AlMasaOperation.query.get_or_404(op_id)
    crane_id = operation.crane_id
    AlMasaCheckOperation.query.filter_by(operation_id=op_id).delete()
    db.session.delete(operation)
    db.session.commit()
    flash('تم حذف العملية بنجاح', 'success')
    return redirect(url_for('almasa_crane_detail', crane_id=crane_id))

@app.route('/almasa/operations/<int:op_id>/edit', methods=['POST'])
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_operation_edit(op_id):
    operation = AlMasaOperation.query.get_or_404(op_id)
    operation.start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
    operation.end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date() if request.form.get('end_date') else None
    operation.actual_daily_value = float(request.form.get('actual_daily_value', 0))
    operation.default_daily_value = float(request.form.get('default_daily_value', 0))
    operation.days_count = int(request.form.get('days_count', 0))
    operation.actual_total = operation.actual_daily_value * operation.days_count
    operation.default_total = operation.default_daily_value * operation.days_count
    db.session.commit()
    flash('تم تعديل العملية بنجاح', 'success')
    return redirect(url_for('almasa_crane_detail', crane_id=operation.crane_id))

@app.route('/almasa/expenses/add', methods=['POST'])
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_add_expense():
    crane_id = int(request.form.get('crane_id'))
    date_str = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
    expense_type = request.form.get('expense_type')
    amount = float(request.form.get('amount', 0))
    notes = request.form.get('notes')
    expense = AlMasaExpense(
        crane_id=crane_id, date=date_str, expense_type=expense_type,
        amount=amount, notes=notes, created_by=current_user.id
    )
    db.session.add(expense)
    db.session.commit()
    flash('تم إضافة المصروف بنجاح', 'success')
    return redirect(url_for('almasa_crane_detail', crane_id=crane_id))

@app.route('/almasa/expenses/<int:exp_id>/delete', methods=['POST'])
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_expense_delete(exp_id):
    expense = AlMasaExpense.query.get_or_404(exp_id)
    crane_id = expense.crane_id
    db.session.delete(expense)
    db.session.commit()
    flash('تم حذف المصروف بنجاح', 'success')
    return redirect(url_for('almasa_crane_detail', crane_id=crane_id))

@app.route('/almasa/expenses/<int:exp_id>/edit', methods=['POST'])
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_expense_edit(exp_id):
    expense = AlMasaExpense.query.get_or_404(exp_id)
    expense.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
    expense.expense_type = request.form.get('expense_type')
    expense.amount = float(request.form.get('amount', 0))
    expense.notes = request.form.get('notes')
    db.session.commit()
    flash('تم تعديل المصروف بنجاح', 'success')
    return redirect(url_for('almasa_crane_detail', crane_id=expense.crane_id))

@app.route('/almasa/checks/add', methods=['POST'])
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_add_check():
    crane_id = int(request.form.get('crane_id'))
    check_number = request.form.get('check_number')
    company_name = request.form.get('company_name')
    due_date = datetime.strptime(request.form.get('due_date'), '%Y-%m-%d').date()
    operation_ids = request.form.getlist('operation_ids[]')
    total_actual = 0
    for op_id in operation_ids:
        operation = AlMasaOperation.query.get(int(op_id))
        if operation:
            total_actual += operation.actual_total
    check_amount = total_actual + (total_actual * 0.14)
    check = AlMasaCheck(
        crane_id=crane_id, check_number=check_number, company_name=company_name,
        amount=check_amount, due_date=due_date, status='معلق'
    )
    db.session.add(check)
    db.session.flush()
    for op_id in operation_ids:
        check_op = AlMasaCheckOperation(check_id=check.id, operation_id=int(op_id))
        db.session.add(check_op)
    db.session.commit()
    flash('تم إضافة الشيك بنجاح', 'success')
    return redirect(url_for('almasa_crane_detail', crane_id=crane_id))

@app.route('/almasa/checks/<int:check_id>/delete', methods=['POST'])
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_check_delete(check_id):
    check = AlMasaCheck.query.get_or_404(check_id)
    crane_id = check.crane_id
    AlMasaCheckOperation.query.filter_by(check_id=check_id).delete()
    db.session.delete(check)
    db.session.commit()
    flash('تم حذف الشيك بنجاح', 'success')
    return redirect(url_for('almasa_crane_detail', crane_id=crane_id))

@app.route('/almasa/checks/<int:check_id>/report')
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_check_report(check_id):
    check = AlMasaCheck.query.get_or_404(check_id)
    crane = AlMasaCrane.query.get(check.crane_id)
    check_operations = AlMasaCheckOperation.query.filter_by(check_id=check_id).all()
    operations_list = []
    total_actual = 0
    total_default = 0
    total_days = 0
    for co in check_operations:
        operation = AlMasaOperation.query.get(co.operation_id)
        if operation:
            operations_list.append(operation)
            total_actual += operation.actual_total
            total_default += operation.default_total
            total_days += operation.days_count
    if operations_list:
        min_date = min(o.start_date for o in operations_list)
        dates_with_end = [o.end_date for o in operations_list if o.end_date]
        max_date = max(dates_with_end) if dates_with_end else max(o.start_date for o in operations_list)
        expenses = AlMasaExpense.query.filter(
            AlMasaExpense.crane_id == check.crane_id,
            AlMasaExpense.date >= min_date,
            AlMasaExpense.date <= max_date
        ).all()
    else:
        expenses = []
    total_expenses = sum(e.amount for e in expenses)
    partners = AlMasaPartner.query.filter_by(crane_id=check.crane_id).all()
    non_basic = [p for p in partners if not p.is_basic]
    if len(non_basic) == 0:
        total_default = total_actual
    check_amount = total_actual + (total_actual * 0.14)
    tax_14 = total_actual * 0.14
    net_actual = total_actual - total_expenses
    net_default = total_default - (total_default * 0.085) - total_expenses
    basic_diff = (net_actual - net_default) / 2
    partners_profit = []
    for p in partners:
        if p.is_basic:
            actual_share = basic_diff
            default_share = net_default * (p.percentage / 100)
        else:
            actual_share = 0
            default_share = net_default * (p.percentage / 100)
        partners_profit.append({
            'partner': p,
            'actual_share': actual_share,
            'default_share': default_share,
            'total_share': actual_share + default_share
        })
    return render_template('almasa/check_report.html',
                           check=check, crane=crane,
                           operations=operations_list, expenses=expenses,
                           total_actual=total_actual, total_default=total_default,
                           total_days=total_days, total_expenses=total_expenses,
                           check_amount=check_amount, tax_14=tax_14,
                           net_actual=net_actual, net_default=net_default,
                           basic_diff=basic_diff,
                           partners=partners, partners_profit=partners_profit,
                           report_type='partnership')

@app.route('/almasa/reports')
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_reports():
    partnership_cranes = AlMasaCrane.query.filter_by(crane_type='partnership').all()
    private_cranes = AlMasaPrivateCrane.query.all()
    supplies = AlMasaSupply.query.all()
    return render_template('almasa/reports.html',
                           partnership_cranes=partnership_cranes,
                           private_cranes=private_cranes,
                           supplies=supplies)

@app.route('/almasa/reports/crane/<int:crane_id>')
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_crane_report(crane_id):
    crane = AlMasaCrane.query.get_or_404(crane_id)
    operations = AlMasaOperation.query.filter_by(crane_id=crane_id).order_by(AlMasaOperation.start_date.asc()).all()
    expenses = AlMasaExpense.query.filter_by(crane_id=crane_id).order_by(AlMasaExpense.date.asc()).all()
    partners = AlMasaPartner.query.filter_by(crane_id=crane_id).all()
    total_actual = sum(o.actual_total for o in operations)
    total_default = sum(o.default_total for o in operations)
    total_expenses = sum(e.amount for e in expenses)
    non_basic = [p for p in partners if not p.is_basic]
    if len(non_basic) == 0:
        total_default = total_actual
    net_actual = total_actual - total_expenses
    net_default = total_default - (total_default * 0.085) - total_expenses
    basic_diff = (net_actual - net_default) / 2
    partners_profit = []
    for p in partners:
        if p.is_basic:
            actual_share = basic_diff
            default_share = net_default * (p.percentage / 100)
        else:
            actual_share = 0
            default_share = net_default * (p.percentage / 100)
        partners_profit.append({
            'partner': p,
            'actual_share': actual_share,
            'default_share': default_share,
            'total_share': actual_share + default_share
        })
    return render_template('almasa/crane_report.html',
                           crane=crane, operations=operations, expenses=expenses,
                           partners=partners, total_actual=total_actual,
                           total_default=total_default, total_expenses=total_expenses,
                           net_actual=net_actual, net_default=net_default,
                           basic_diff=basic_diff, partners_profit=partners_profit,
                           report_type='partnership')

@app.route('/almasa/private-cranes', methods=['GET', 'POST'])
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_private_cranes():
    if request.method == 'POST':
        name = request.form.get('name')
        owner_name = request.form.get('owner_name')
        notes = request.form.get('notes')
        new_crane = AlMasaPrivateCrane(name=name, owner_name=owner_name, notes=notes)
        db.session.add(new_crane)
        db.session.commit()
        flash('تم إضافة الونش الخاص بنجاح', 'success')
        return redirect(url_for('almasa_private_cranes'))
    cranes = AlMasaPrivateCrane.query.order_by(AlMasaPrivateCrane.id.asc()).all()
    return render_template('almasa/private_cranes.html', cranes=cranes)

@app.route('/almasa/private-cranes/<int:crane_id>')
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_private_crane_detail(crane_id):
    crane = AlMasaPrivateCrane.query.get_or_404(crane_id)
    operations = AlMasaPrivateOperation.query.filter_by(crane_id=crane_id).order_by(AlMasaPrivateOperation.start_date.asc()).all()
    checks = AlMasaPrivateCheck.query.filter_by(crane_id=crane_id).order_by(AlMasaPrivateCheck.due_date.asc()).all()
    expenses = AlMasaPrivateExpense.query.filter_by(crane_id=crane_id).order_by(AlMasaPrivateExpense.date.asc()).all()
    return render_template('almasa/private_crane_detail.html',
                           crane=crane, operations=operations,
                           checks=checks, expenses=expenses)

@app.route('/almasa/private-cranes/<int:crane_id>/delete', methods=['POST'])
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_private_crane_delete(crane_id):
    crane = AlMasaPrivateCrane.query.get_or_404(crane_id)
    db.session.delete(crane)
    db.session.commit()
    flash('تم حذف الونش الخاص بنجاح', 'success')
    return redirect(url_for('almasa_private_cranes'))

@app.route('/almasa/private-operations/add', methods=['POST'])
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_add_private_operation():
    crane_id = int(request.form.get('crane_id'))
    start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
    end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date() if request.form.get('end_date') else None
    actual_daily = float(request.form.get('actual_daily_value', 0))
    default_daily = float(request.form.get('default_daily_value', 0))
    days_count = int(request.form.get('days_count', 0))
    actual_total = actual_daily * days_count
    default_total = default_daily * days_count
    operation = AlMasaPrivateOperation(
        crane_id=crane_id, start_date=start_date, end_date=end_date,
        actual_daily_value=actual_daily, default_daily_value=default_daily,
        days_count=days_count, actual_total=actual_total, default_total=default_total,
        created_by=current_user.id
    )
    db.session.add(operation)
    db.session.commit()
    flash('تم إضافة العملية بنجاح', 'success')
    return redirect(url_for('almasa_private_crane_detail', crane_id=crane_id))

@app.route('/almasa/private-operations/<int:op_id>/delete', methods=['POST'])
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_private_operation_delete(op_id):
    operation = AlMasaPrivateOperation.query.get_or_404(op_id)
    crane_id = operation.crane_id
    AlMasaPrivateCheckOperation.query.filter_by(operation_id=op_id).delete()
    db.session.delete(operation)
    db.session.commit()
    flash('تم حذف العملية بنجاح', 'success')
    return redirect(url_for('almasa_private_crane_detail', crane_id=crane_id))

@app.route('/almasa/private-operations/<int:op_id>/edit', methods=['POST'])
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_private_operation_edit(op_id):
    operation = AlMasaPrivateOperation.query.get_or_404(op_id)
    operation.start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
    operation.end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date() if request.form.get('end_date') else None
    operation.actual_daily_value = float(request.form.get('actual_daily_value', 0))
    operation.default_daily_value = float(request.form.get('default_daily_value', 0))
    operation.days_count = int(request.form.get('days_count', 0))
    operation.actual_total = operation.actual_daily_value * operation.days_count
    operation.default_total = operation.default_daily_value * operation.days_count
    db.session.commit()
    flash('تم تعديل العملية بنجاح', 'success')
    return redirect(url_for('almasa_private_crane_detail', crane_id=operation.crane_id))

@app.route('/almasa/private-expenses/add', methods=['POST'])
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_add_private_expense():
    crane_id = int(request.form.get('crane_id'))
    date_str = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
    expense_type = request.form.get('expense_type')
    amount = float(request.form.get('amount', 0))
    notes = request.form.get('notes')
    expense = AlMasaPrivateExpense(
        crane_id=crane_id, date=date_str, expense_type=expense_type,
        amount=amount, notes=notes, created_by=current_user.id
    )
    db.session.add(expense)
    db.session.commit()
    flash('تم إضافة المصروف بنجاح', 'success')
    return redirect(url_for('almasa_private_crane_detail', crane_id=crane_id))

@app.route('/almasa/private-expenses/<int:exp_id>/delete', methods=['POST'])
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_private_expense_delete(exp_id):
    expense = AlMasaPrivateExpense.query.get_or_404(exp_id)
    crane_id = expense.crane_id
    db.session.delete(expense)
    db.session.commit()
    flash('تم حذف المصروف بنجاح', 'success')
    return redirect(url_for('almasa_private_crane_detail', crane_id=crane_id))

@app.route('/almasa/private-expenses/<int:exp_id>/edit', methods=['POST'])
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_private_expense_edit(exp_id):
    expense = AlMasaPrivateExpense.query.get_or_404(exp_id)
    expense.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
    expense.expense_type = request.form.get('expense_type')
    expense.amount = float(request.form.get('amount', 0))
    expense.notes = request.form.get('notes')
    db.session.commit()
    flash('تم تعديل المصروف بنجاح', 'success')
    return redirect(url_for('almasa_private_crane_detail', crane_id=expense.crane_id))

@app.route('/almasa/private-checks/add', methods=['POST'])
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_add_private_check():
    crane_id = int(request.form.get('crane_id'))
    check_number = request.form.get('check_number')
    company_name = request.form.get('company_name')
    due_date = datetime.strptime(request.form.get('due_date'), '%Y-%m-%d').date()
    operation_ids = request.form.getlist('operation_ids[]')
    total_actual = 0
    for op_id in operation_ids:
        operation = AlMasaPrivateOperation.query.get(int(op_id))
        if operation:
            total_actual += operation.actual_total
    check_amount = total_actual + (total_actual * 0.14)
    check = AlMasaPrivateCheck(
        crane_id=crane_id, check_number=check_number, company_name=company_name,
        amount=check_amount, due_date=due_date, status='معلق'
    )
    db.session.add(check)
    db.session.flush()
    for op_id in operation_ids:
        check_op = AlMasaPrivateCheckOperation(check_id=check.id, operation_id=int(op_id))
        db.session.add(check_op)
    db.session.commit()
    flash('تم إضافة الشيك بنجاح', 'success')
    return redirect(url_for('almasa_private_crane_detail', crane_id=crane_id))

@app.route('/almasa/private-checks/<int:check_id>/delete', methods=['POST'])
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_private_check_delete(check_id):
    check = AlMasaPrivateCheck.query.get_or_404(check_id)
    crane_id = check.crane_id
    AlMasaPrivateCheckOperation.query.filter_by(check_id=check_id).delete()
    db.session.delete(check)
    db.session.commit()
    flash('تم حذف الشيك بنجاح', 'success')
    return redirect(url_for('almasa_private_crane_detail', crane_id=crane_id))

@app.route('/almasa/private-checks/<int:check_id>/report')
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_private_check_report(check_id):
    check = AlMasaPrivateCheck.query.get_or_404(check_id)
    crane = AlMasaPrivateCrane.query.get(check.crane_id)
    check_operations = AlMasaPrivateCheckOperation.query.filter_by(check_id=check_id).all()
    operations_list = []
    total_actual = 0
    total_default = 0
    total_days = 0
    for co in check_operations:
        operation = AlMasaPrivateOperation.query.get(co.operation_id)
        if operation:
            operations_list.append(operation)
            total_actual += operation.actual_total
            total_default += operation.default_total
            total_days += operation.days_count
    if operations_list:
        min_date = min(o.start_date for o in operations_list)
        dates_with_end = [o.end_date for o in operations_list if o.end_date]
        max_date = max(dates_with_end) if dates_with_end else max(o.start_date for o in operations_list)
        expenses = AlMasaPrivateExpense.query.filter(
            AlMasaPrivateExpense.crane_id == check.crane_id,
            AlMasaPrivateExpense.date >= min_date,
            AlMasaPrivateExpense.date <= max_date
        ).all()
    else:
        expenses = []
    total_expenses = sum(e.amount for e in expenses)
    total_default = total_actual
    check_amount = total_actual + (total_actual * 0.14)
    tax_14 = total_actual * 0.14
    net_actual = total_actual - total_expenses
    net_default = total_default - (total_default * 0.085) - total_expenses
    owner_share = net_actual
    return render_template('almasa/check_report.html',
                           check=check, crane=crane,
                           operations=operations_list, expenses=expenses,
                           total_actual=total_actual, total_default=total_default,
                           total_days=total_days, total_expenses=total_expenses,
                           check_amount=check_amount, tax_14=tax_14,
                           net_actual=net_actual, net_default=net_default,
                           owner_share=owner_share,
                           report_type='private')

@app.route('/almasa/reports/private-crane/<int:crane_id>')
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_private_crane_report(crane_id):
    crane = AlMasaPrivateCrane.query.get_or_404(crane_id)
    operations = AlMasaPrivateOperation.query.filter_by(crane_id=crane_id).order_by(AlMasaPrivateOperation.start_date.asc()).all()
    expenses = AlMasaPrivateExpense.query.filter_by(crane_id=crane_id).order_by(AlMasaPrivateExpense.date.asc()).all()
    total_actual = sum(o.actual_total for o in operations)
    total_default = total_actual
    total_expenses = sum(e.amount for e in expenses)
    net_actual = total_actual - total_expenses
    net_default = total_default - (total_default * 0.085) - total_expenses
    owner_share = net_actual
    return render_template('almasa/private_crane_report.html',
                           crane=crane, operations=operations, expenses=expenses,
                           total_actual=total_actual, total_default=total_default,
                           total_expenses=total_expenses, net_actual=net_actual,
                           net_default=net_default, owner_share=owner_share)

@app.route('/almasa/supplies', methods=['GET', 'POST'])
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_supplies():
    if request.method == 'POST':
        name = request.form.get('name')
        supplier_name = request.form.get('supplier_name')
        customer_name = request.form.get('customer_name')
        notes = request.form.get('notes')
        new_supply = AlMasaSupply(name=name, supplier_name=supplier_name,
                                   customer_name=customer_name, notes=notes)
        db.session.add(new_supply)
        db.session.commit()
        flash('تم إضافة التوريدة بنجاح', 'success')
        return redirect(url_for('almasa_supplies'))
    supplies = AlMasaSupply.query.order_by(AlMasaSupply.id.asc()).all()
    return render_template('almasa/supplies.html', supplies=supplies)

@app.route('/almasa/supplies/<int:supply_id>')
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_supply_detail(supply_id):
    supply = AlMasaSupply.query.get_or_404(supply_id)
    operations = AlMasaSupplyOperation.query.filter_by(supply_id=supply_id).order_by(AlMasaSupplyOperation.start_date.asc()).all()
    expenses = AlMasaSupplyExpense.query.filter_by(supply_id=supply_id).order_by(AlMasaSupplyExpense.date.asc()).all()
    return render_template('almasa/supply_detail.html',
                           supply=supply, operations=operations, expenses=expenses)

@app.route('/almasa/supplies/<int:supply_id>/delete', methods=['POST'])
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_supply_delete(supply_id):
    supply = AlMasaSupply.query.get_or_404(supply_id)
    db.session.delete(supply)
    db.session.commit()
    flash('تم حذف التوريدة بنجاح', 'success')
    return redirect(url_for('almasa_supplies'))

@app.route('/almasa/supply-operations/add', methods=['POST'])
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_add_supply_operation():
    supply_id = int(request.form.get('supply_id'))
    start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
    end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date() if request.form.get('end_date') else None
    days_count = int(request.form.get('days_count', 0))
    supplier_daily = float(request.form.get('supplier_daily_rate', 0))
    customer_daily = float(request.form.get('customer_daily_rate', 0))
    supplier_total = supplier_daily * days_count
    customer_total = customer_daily * days_count
    operation = AlMasaSupplyOperation(
        supply_id=supply_id, start_date=start_date, end_date=end_date,
        days_count=days_count, supplier_daily_rate=supplier_daily,
        customer_daily_rate=customer_daily,
        supplier_total=supplier_total, customer_total=customer_total,
        created_by=current_user.id
    )
    db.session.add(operation)
    db.session.commit()
    flash('تم إضافة العملية بنجاح', 'success')
    return redirect(url_for('almasa_supply_detail', supply_id=supply_id))

@app.route('/almasa/supply-operations/<int:op_id>/delete', methods=['POST'])
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_supply_operation_delete(op_id):
    operation = AlMasaSupplyOperation.query.get_or_404(op_id)
    supply_id = operation.supply_id
    db.session.delete(operation)
    db.session.commit()
    flash('تم حذف العملية بنجاح', 'success')
    return redirect(url_for('almasa_supply_detail', supply_id=supply_id))

@app.route('/almasa/supply-operations/<int:op_id>/edit', methods=['POST'])
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_supply_operation_edit(op_id):
    operation = AlMasaSupplyOperation.query.get_or_404(op_id)
    operation.start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
    operation.end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date() if request.form.get('end_date') else None
    operation.days_count = int(request.form.get('days_count', 0))
    operation.supplier_daily_rate = float(request.form.get('supplier_daily_rate', 0))
    operation.customer_daily_rate = float(request.form.get('customer_daily_rate', 0))
    operation.supplier_total = operation.supplier_daily_rate * operation.days_count
    operation.customer_total = operation.customer_daily_rate * operation.days_count
    db.session.commit()
    flash('تم تعديل العملية بنجاح', 'success')
    return redirect(url_for('almasa_supply_detail', supply_id=operation.supply_id))

@app.route('/almasa/supply-expenses/add', methods=['POST'])
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_add_supply_expense():
    supply_id = int(request.form.get('supply_id'))
    date_str = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
    expense_type = request.form.get('expense_type')
    amount = float(request.form.get('amount', 0))
    notes = request.form.get('notes')
    expense = AlMasaSupplyExpense(
        supply_id=supply_id, date=date_str, expense_type=expense_type,
        amount=amount, notes=notes, created_by=current_user.id
    )
    db.session.add(expense)
    db.session.commit()
    flash('تم إضافة المصروف بنجاح', 'success')
    return redirect(url_for('almasa_supply_detail', supply_id=supply_id))

@app.route('/almasa/supply-expenses/<int:exp_id>/delete', methods=['POST'])
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_supply_expense_delete(exp_id):
    expense = AlMasaSupplyExpense.query.get_or_404(exp_id)
    supply_id = expense.supply_id
    db.session.delete(expense)
    db.session.commit()
    flash('تم حذف المصروف بنجاح', 'success')
    return redirect(url_for('almasa_supply_detail', supply_id=supply_id))

@app.route('/almasa/supply-expenses/<int:exp_id>/edit', methods=['POST'])
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_supply_expense_edit(exp_id):
    expense = AlMasaSupplyExpense.query.get_or_404(exp_id)
    expense.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
    expense.expense_type = request.form.get('expense_type')
    expense.amount = float(request.form.get('amount', 0))
    expense.notes = request.form.get('notes')
    db.session.commit()
    flash('تم تعديل المصروف بنجاح', 'success')
    return redirect(url_for('almasa_supply_detail', supply_id=expense.supply_id))

@app.route('/almasa/supplies/<int:supply_id>/report')
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_supply_report(supply_id):
    supply = AlMasaSupply.query.get_or_404(supply_id)
    operations = AlMasaSupplyOperation.query.filter_by(supply_id=supply_id).order_by(AlMasaSupplyOperation.start_date.asc()).all()
    expenses = AlMasaSupplyExpense.query.filter_by(supply_id=supply_id).order_by(AlMasaSupplyExpense.date.asc()).all()
    total_customer = sum(o.customer_total for o in operations)
    total_supplier = sum(o.supplier_total for o in operations)
    total_expenses = sum(e.amount for e in expenses)
    check_amount = total_customer
    tax_14 = check_amount * 0.14
    tax_85 = check_amount * 0.085
    net_after_tax = check_amount - tax_14 - tax_85
    net_after_expenses = net_after_tax - total_expenses
    our_profit = net_after_expenses - total_supplier
    per_person = our_profit / 2
    return render_template('almasa/supply_report.html',
                           supply=supply, operations=operations, expenses=expenses,
                           total_customer=total_customer, total_supplier=total_supplier,
                           total_expenses=total_expenses, check_amount=check_amount,
                           tax_14=tax_14, tax_85=tax_85,
                           net_after_tax=net_after_tax,
                           net_after_expenses=net_after_expenses,
                           our_profit=our_profit, per_person=per_person)

@app.route('/almasa/partner-accounts', methods=['GET', 'POST'])
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_partner_accounts():
    if request.method == 'POST':
        if request.form.get('delete_id'):
            record_id = int(request.form.get('delete_id'))
            record = AlMasaPartnerAccount.query.get_or_404(record_id)
            db.session.delete(record)
            db.session.commit()
            flash('تم الحذف بنجاح', 'success')
            return redirect(url_for('almasa_partner_accounts'))
        if request.form.get('edit_id'):
            record_id = int(request.form.get('edit_id'))
            record = AlMasaPartnerAccount.query.get_or_404(record_id)
            record.person_name = request.form.get('person_name')
            record.person_type = request.form.get('person_type')
            record.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
            record.amount = float(request.form.get('amount', 0))
            record.description = request.form.get('description')
            record.notes = request.form.get('notes')
            db.session.commit()
            flash('تم التعديل بنجاح', 'success')
            return redirect(url_for('almasa_partner_accounts'))
        person_name = request.form.get('person_name')
        person_type = request.form.get('person_type', 'شريك')
        date_str = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        amount = float(request.form.get('amount', 0))
        description = request.form.get('description')
        notes = request.form.get('notes')
        new_record = AlMasaPartnerAccount(
            person_name=person_name, person_type=person_type, date=date_str,
            amount=amount, description=description, notes=notes,
            created_by=current_user.id
        )
        db.session.add(new_record)
        db.session.commit()
        flash('تم إضافة السجل بنجاح', 'success')
        return redirect(url_for('almasa_partner_accounts'))
    records = AlMasaPartnerAccount.query.order_by(AlMasaPartnerAccount.date.desc()).all()
    return render_template('almasa/partner_accounts.html', records=records)

@app.route('/almasa/partner-accounts/person/<string:person_name>')
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_person_report(person_name):
    records = AlMasaPartnerAccount.query.filter_by(person_name=person_name).order_by(AlMasaPartnerAccount.date.asc()).all()
    total = sum(r.amount for r in records)
    return render_template('almasa/person_report.html',
                           person_name=person_name, records=records, total=total)

# ==================== التشغيل ====================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
