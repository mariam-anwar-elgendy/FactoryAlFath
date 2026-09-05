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

from models import db, User, Category, Size, Thickness, Supplier, Customer
from models import FactoryRawMaterial, FactoryProduction, FactoryDiary
from models import StoreSale, StorePurchase, StoreInventory, StoreReceiving, StoreReturn, StoreDiary
from models import StoreSaleItem, StorePurchaseItem, Payment
from models import TreasuryAccount, TreasuryTransaction, TreasuryTransfer
from models import EditLog, Notification, ActivityLog
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

# ==================== دوال مساعدة للخزينة ====================
def get_or_create_treasury_account(person_name, account_type):
    account = TreasuryAccount.query.filter_by(person_name=person_name, account_type=account_type).first()
    if not account:
        account = TreasuryAccount(person_name=person_name, account_type=account_type, balance=0)
        db.session.add(account)
        db.session.commit()
    return account

def get_visible_accounts_for_current_user():
    if current_user.role in ['meg', 'admin', 'mariam']:
        return TreasuryAccount.query.all()
    elif current_user.role == 'ahmed':
        return TreasuryAccount.query.filter_by(person_name='الحاج أحمد').all()
    elif current_user.role == 'eid':
        return TreasuryAccount.query.filter_by(person_name='عيد').all()
    elif current_user.role == 'abdo':
        return TreasuryAccount.query.filter_by(person_name='عبدالله').all()
    else:
        return []

# ==================== صلاحية الحذف ====================
def can_delete_record(user_role, record_date=None):
    if user_role in ['meg', 'admin', 'mariam']:
        return True
    if user_role == 'rehab':
        if record_date:
            return (datetime.now().date() - record_date).days <= 7
        return False
    return False

# ==================== تسجيل النشاط ====================
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
        try:
            db.session.execute(db.text('ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR(20)'))
            db.session.execute(db.text('ALTER TABLE users ADD COLUMN IF NOT EXISTS last_activity TIMESTAMP'))
            db.session.commit()
        except:
            pass
        
        # حذف الأعمدة القديمة من store_sales
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
            print("✅ تم حذف الأعمدة القديمة من store_sales")
        except Exception as e:
            db.session.rollback()
            print(f"⚠️ ملاحظة store_sales: {e}")
        
        # حذف الأعمدة القديمة من store_purchases
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
            print("✅ تم حذف الأعمدة القديمة من store_purchases")
        except Exception as e:
            db.session.rollback()
            print(f"⚠️ ملاحظة store_purchases: {e}")

        users_data = [
            {'username': os.environ.get('MEG_USERNAME', 'meg'),
             'password': os.environ.get('MEG_PASSWORD', '262004'),
             'full_name': 'MEG',
             'role': 'meg',
             'is_hidden': True},
            {'username': os.environ.get('ADMIN_USERNAME', 'f'),
             'password': os.environ.get('ADMIN_PASSWORD', '*1997#'),
             'full_name': 'Admin',
             'role': 'admin',
             'is_hidden': False},
            {'username': os.environ.get('MARIAM_USERNAME', 'mariam'),
             'password': os.environ.get('MARIAM_PASSWORD', '#mariam2004'),
             'full_name': 'Mariam',
             'role': 'mariam',
             'is_hidden': False},
            {'username': os.environ.get('REHAB_USERNAME', 'rehab'),
             'password': os.environ.get('REHAB_PASSWORD', 'rehab2004#'),
             'full_name': 'Rehab',
             'role': 'rehab',
             'is_hidden': False},
            {'username': os.environ.get('MOHAMED_USERNAME', 'mohamed'),
             'password': os.environ.get('MOHAMED_PASSWORD', 'mohamed123#'),
             'full_name': 'Mohamed',
             'role': 'mohamed',
             'is_hidden': False},
            {'username': os.environ.get('AHMED_USERNAME', 'a'),
             'password': os.environ.get('AHMED_PASSWORD', '#123456#'),
             'full_name': 'الحاج أحمد',
             'role': 'ahmed',
             'is_hidden': False},
            {'username': os.environ.get('EID_USERNAME', 'eid'),
             'password': os.environ.get('EID_PASSWORD', 'eid123#'),
             'full_name': 'عيد',
             'role': 'eid',
             'is_hidden': False},
            {'username': os.environ.get('ABDO_USERNAME', 'abdo'),
             'password': os.environ.get('ABDO_PASSWORD', 'abdo123#'),
             'full_name': 'عبدالله',
             'role': 'abdo',
             'is_hidden': False},
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

        name_mapping = {
            'Ahmed': 'الحاج أحمد',
            'ahmed': 'الحاج أحمد',
            'Eid': 'عيد',
            'eid': 'عيد',
            'Abdo': 'عبدالله',
            'abdo': 'عبدالله',
        }

        for old_name, new_name in name_mapping.items():
            old_accounts = TreasuryAccount.query.filter_by(person_name=old_name).all()
            for old_acc in old_accounts:
                arabic_acc = TreasuryAccount.query.filter_by(person_name=new_name, account_type=old_acc.account_type).first()
                if arabic_acc:
                    arabic_acc.balance += old_acc.balance
                    for txn in old_acc.transactions:
                        txn.account_id = arabic_acc.id
                    db.session.delete(old_acc)
                else:
                    old_acc.person_name = new_name
            db.session.commit()

init_db()

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
            if user.role != 'admin':
                admin_user = User.query.filter_by(role='admin').first()
                if admin_user:
                    notification = Notification(user_id=admin_user.id, message=f"تم تسجيل دخول {user.full_name} ({user.role})")
                    db.session.add(notification)
                    db.session.commit()
            flash(f'مرحباً {user.full_name} 👋', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('اسم المستخدم أو كلمة المرور غير صحيحة', 'danger')
    return render_template('login.html')

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
    stats = {
        'raw_materials_count': FactoryRawMaterial.query.count() if role in ['meg','admin','mariam','rehab','mohamed'] else 0,
        'production_count': FactoryProduction.query.count() if role in ['meg','admin','mariam','rehab','mohamed'] else 0,
        'sales_count': StoreSale.query.count() if role in ['meg','admin','mariam','rehab','ahmed'] else 0,
        'purchases_count': StorePurchase.query.count() if role in ['meg','admin','mariam','rehab','ahmed'] else 0,
        'customers_count': Customer.query.count() if role in ['meg','admin','mariam','rehab','ahmed'] else 0,
        'suppliers_count': Supplier.query.count() if role in ['meg','admin','mariam','rehab','ahmed'] else 0,
        'treasury_balance': 0,
        'today_sales': db.session.query(db.func.sum(StoreSaleItem.total)).join(StoreSale).filter(StoreSale.date == date.today()).scalar() or 0,
        'today_purchases': db.session.query(db.func.sum(StorePurchaseItem.total)).join(StorePurchase).filter(StorePurchase.date == date.today()).scalar() or 0,
        'low_inventory_count': StoreInventory.query.filter(StoreInventory.current_quantity <= StoreInventory.min_quantity).count() if role in ['meg','admin','mariam','rehab','ahmed'] else 0,
    }

    if role in ['meg', 'admin', 'mariam']:
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
@role_required('meg', 'admin', 'mariam', 'rehab', 'mohamed')
def factory_index():
    today = date.today()
    raw_materials = FactoryRawMaterial.query.filter_by(date=today).order_by(FactoryRawMaterial.id.asc()).all()
    production = FactoryProduction.query.filter_by(date=today).order_by(FactoryProduction.id.asc()).all()
    diary = FactoryDiary.query.filter_by(date=today).order_by(FactoryDiary.id.asc()).all()
    return render_template('factory/index.html', raw_materials=raw_materials, production=production, diary=diary)

@app.route('/factory/raw-materials', methods=['GET', 'POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab', 'mohamed')
def factory_raw_materials():
    if request.method == 'POST':
        if request.form.get('delete_id'):
            record_id = int(request.form.get('delete_id'))
            record = FactoryRawMaterial.query.get_or_404(record_id)
            if can_delete_record(current_user.role, record.date):
                db.session.delete(record)
                db.session.commit()
                log_activity(current_user.id, 'delete', f"حذف وارد ماسورة {record.pipe_size} {record.pipe_thickness}")
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
                log_activity(current_user.id, 'edit', f"تعديل وارد ماسورة {record.pipe_size}")
                flash('تم تحديث السجل بنجاح', 'success')
            else:
                flash('غير مصرح لك بالتعديل أو انتهت صلاحية التعديل', 'danger')
            return redirect(url_for('factory_raw_materials'))
        record_date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        pipe_size = request.form.get('pipe_size')
        pipe_thickness = request.form.get('pipe_thickness')
        quantity = float(request.form.get('quantity', 0))
        supplier = request.form.get('supplier')
        notes = request.form.get('notes')
        
        # إضافة المورد تلقائياً إذا كان جديد
        if supplier and not Supplier.query.filter_by(name=supplier).first():
            db.session.add(Supplier(name=supplier))
            print(f"✅ تم إضافة مورد جديد: {supplier}")
        
        new_record = FactoryRawMaterial(date=record_date, pipe_size=pipe_size, pipe_thickness=pipe_thickness,
                                        quantity=quantity, supplier=supplier, notes=notes,
                                        created_by=current_user.id, created_at=datetime.utcnow())
        db.session.add(new_record)
        db.session.commit()
        log_activity(current_user.id, 'create', f"إضافة وارد ماسورة {pipe_size} {pipe_thickness} كمية {quantity}")
        row_data = [record_date.strftime('%Y-%m-%d'), 'وارد', pipe_size, pipe_thickness, quantity, supplier, notes, current_user.full_name]
        excel_path = add_row_to_excel('يوميات المصنع.xlsx', ['التاريخ', 'الوصف', 'المقاس', 'السماكة', 'الكمية', 'المورد', 'ملاحظات', 'المسؤول'], row_data)
        if excel_path: drive_service.upload_file(excel_path, 'يوميات المصنع.xlsx')
        flash('تم إضافة وارد المواسير بنجاح', 'success')
        return redirect(url_for('factory_raw_materials'))
    materials = FactoryRawMaterial.query.order_by(FactoryRawMaterial.date.asc(), FactoryRawMaterial.id.asc()).all()
    suppliers = Supplier.query.order_by(Supplier.name.asc()).all()
    return render_template('factory/raw_materials.html', materials=materials, suppliers=suppliers)

@app.route('/factory/production', methods=['GET', 'POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab', 'mohamed')
def factory_production():
    if request.method == 'POST':
        if request.form.get('delete_id'):
            record_id = int(request.form.get('delete_id'))
            record = FactoryProduction.query.get_or_404(record_id)
            if can_delete_record(current_user.role, record.date):
                db.session.delete(record)
                db.session.commit()
                log_activity(current_user.id, 'delete', f"حذف إنتاج {record.elbow_size}")
                flash('تم حذف السجل بنجاح', 'success')
            else:
                flash('غير مصرح لك بالحذف', 'danger')
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
                log_activity(current_user.id, 'edit', f"تعديل إنتاج {record.elbow_size}")
                flash('تم تحديث السجل بنجاح', 'success')
            else:
                flash('غير مصرح لك بالتعديل أو انتهت صلاحية التعديل', 'danger')
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
        log_activity(current_user.id, 'create', f"إضافة إنتاج {elbow_size} كمية {quantity}")
        row_data = [record_date.strftime('%Y-%m-%d'), 'إنتاج', elbow_size, elbow_thickness, quantity, raw_material_used, notes, current_user.full_name]
        excel_path = add_row_to_excel('يوميات المصنع.xlsx', ['التاريخ', 'الوصف', 'المقاس', 'السماكة', 'الكمية', 'خام مستخدم', 'ملاحظات', 'المسؤول'], row_data)
        if excel_path: drive_service.upload_file(excel_path, 'يوميات المصنع.xlsx')
        flash('تم تسجيل الإنتاج بنجاح', 'success')
        return redirect(url_for('factory_production'))
    production = FactoryProduction.query.order_by(FactoryProduction.date.asc(), FactoryProduction.id.asc()).all()
    return render_template('factory/production.html', production=production)

@app.route('/factory/diary', methods=['GET', 'POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab', 'mohamed')
def factory_diary():
    if request.method == 'POST':
        if request.form.get('delete_id'):
            record_id = int(request.form.get('delete_id'))
            record = FactoryDiary.query.get_or_404(record_id)
            if can_delete_record(current_user.role, record.date):
                db.session.delete(record)
                db.session.commit()
                log_activity(current_user.id, 'delete', f"حذف يومية مصنع")
                flash('تم حذف السجل بنجاح', 'success')
            else:
                flash('غير مصرح لك بالحذف', 'danger')
            return redirect(url_for('factory_diary'))
        if request.form.get('edit_id'):
            record_id = int(request.form.get('edit_id'))
            record = FactoryDiary.query.get_or_404(record_id)
            if can_edit(current_user.role, record.date, record.created_by, current_user.id):
                record.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
                record.description = request.form.get('description')
                record.amount = float(request.form.get('amount', 0))
                db.session.commit()
                log_activity(current_user.id, 'edit', f"تعديل يومية مصنع")
                flash('تم تحديث السجل بنجاح', 'success')
            else:
                flash('غير مصرح لك بالتعديل أو انتهت صلاحية التعديل', 'danger')
            return redirect(url_for('factory_diary'))
        record_date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        
        # استقبال البنود المتعددة
        descriptions = request.form.getlist('description[]')
        amounts = request.form.getlist('amount[]')
        
        for i in range(len(descriptions)):
            if descriptions[i].strip():
                new_record = FactoryDiary(
                    date=record_date,
                    description=descriptions[i],
                    amount=float(amounts[i]) if i < len(amounts) and amounts[i] else 0,
                    created_by=current_user.id,
                    created_at=datetime.utcnow()
                )
                db.session.add(new_record)
        
        db.session.commit()
        log_activity(current_user.id, 'create', f"إضافة يومية مصنع متعددة")
        flash('تم تسجيل اليومية بنجاح', 'success')
        return redirect(url_for('factory_diary'))
    diary = FactoryDiary.query.order_by(FactoryDiary.date.asc(), FactoryDiary.id.asc()).all()
    return render_template('factory/diary.html', diary=diary)

# ==================== المحل ====================
@app.route('/store')
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab', 'ahmed')
def store_index():
    today = date.today()
    sales = StoreSale.query.filter_by(date=today).order_by(StoreSale.id.asc()).all()
    purchases = StorePurchase.query.filter_by(date=today).order_by(StorePurchase.id.asc()).all()
    receiving = StoreReceiving.query.filter_by(date=today).order_by(StoreReceiving.id.asc()).all()
    return render_template('store/index.html', sales=sales, purchases=purchases, receiving=receiving)

# ==================== معاملات المحل ====================
@app.route('/store/transactions', methods=['GET', 'POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab', 'ahmed')
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
                    log_activity(current_user.id, 'delete', f"حذف بيع {record.customer_name}")
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
                    log_activity(current_user.id, 'delete', f"حذف شراء {record.supplier_name}")
                flash('تم الحذف بنجاح', 'success')
            else:
                flash('غير مصرح لك بالحذف', 'danger')
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
                    log_activity(current_user.id, 'edit', f"تعديل بيع {record.customer_name}")
                    flash('تم تعديل البيع بنجاح', 'success')
                else:
                    flash('غير مصرح لك بالتعديل', 'danger')
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
                    log_activity(current_user.id, 'edit', f"تعديل شراء {record.supplier_name}")
                    flash('تم تعديل الشراء بنجاح', 'success')
                else:
                    flash('غير مصرح لك بالتعديل', 'danger')
            return redirect(url_for('store_transactions'))

        # ========== إضافة جديدة ==========
        transaction_type = request.form.get('transaction_type')
        record_date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        party_name = request.form.get('party_name')
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
            # إضافة العميل تلقائياً إذا كان جديد
            if party_name and not Customer.query.filter_by(name=party_name).first():
                db.session.add(Customer(name=party_name, phone=party_phone))
                print(f"✅ تم إضافة عميل جديد: {party_name}")
            
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
            
            log_activity(current_user.id, 'create', f"إضافة بيع لـ {party_name}")
            flash('تم تسجيل البيع بنجاح', 'success')

        else:  # شراء
            # إضافة المورد تلقائياً إذا كان جديد
            if party_name and not Supplier.query.filter_by(name=party_name).first():
                db.session.add(Supplier(name=party_name, phone=party_phone))
                print(f"✅ تم إضافة مورد جديد: {party_name}")
            
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
            
            log_activity(current_user.id, 'create', f"إضافة شراء من {party_name}")
            flash('تم تسجيل الشراء بنجاح', 'success')

        return redirect(url_for('store_transactions'))

    # GET: عرض الصفحة
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

# ==================== دفعات جزئية ====================
@app.route('/payment/add', methods=['POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'ahmed')
def add_payment():
    sale_id = request.form.get('sale_id')
    purchase_id = request.form.get('purchase_id')
    amount = float(request.form.get('amount', 0))
    payment_date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
    notes = request.form.get('notes', '')

    if sale_id:
        sale = StoreSale.query.get_or_404(int(sale_id))
        if amount > sale.remaining:
            flash('المبلغ أكبر من المتبقي', 'danger')
            return redirect(request.referrer)
        payment = Payment(sale_id=sale.id, amount=amount, date=payment_date, notes=notes, created_by=current_user.id)
    elif purchase_id:
        purchase = StorePurchase.query.get_or_404(int(purchase_id))
        if amount > purchase.remaining:
            flash('المبلغ أكبر من المتبقي', 'danger')
            return redirect(request.referrer)
        payment = Payment(purchase_id=purchase.id, amount=amount, date=payment_date, notes=notes, created_by=current_user.id)
    else:
        flash('يجب تحديد الفاتورة', 'danger')
        return redirect(request.referrer)

    db.session.add(payment)
    db.session.commit()
    log_activity(current_user.id, 'create', f"إضافة دفعة بقيمة {amount}")
    flash('تم تسجيل الدفعة بنجاح', 'success')
    return redirect(request.referrer)

# ==================== المخزون ====================
@app.route('/store/inventory', methods=['GET', 'POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab', 'ahmed')
def store_inventory():
    if request.method == 'POST':
        inventory_id = int(request.form.get('inventory_id'))
        item = StoreInventory.query.get_or_404(inventory_id)
        if request.form.get('delete'):
            if current_user.role in ['meg', 'admin', 'mariam']:
                db.session.delete(item)
                db.session.commit()
                log_activity(current_user.id, 'delete', f"حذف مخزون {item.product_type}")
                flash('تم حذف عنصر المخزون', 'success')
            else:
                flash('غير مصرح لك بالحذف', 'danger')
        else:
            item.current_quantity = float(request.form.get('current_quantity', item.current_quantity))
            item.min_quantity = float(request.form.get('min_quantity', item.min_quantity))
            db.session.commit()
            log_activity(current_user.id, 'edit', f"تعديل مخزون {item.product_type}")
            flash('تم تحديث المخزون', 'success')
        return redirect(url_for('store_inventory'))
    inventory = StoreInventory.query.order_by(StoreInventory.product_type.asc(), StoreInventory.product_size.asc()).all()
    return render_template('store/inventory.html', inventory=inventory)

# ==================== مرتجعات ويوميات المحل ====================
@app.route('/store/returns', methods=['GET', 'POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab', 'ahmed')
def store_returns():
    if request.method == 'POST':
        if request.form.get('delete_id'):
            record_id = int(request.form.get('delete_id'))
            record = StoreReturn.query.get_or_404(record_id)
            if can_delete_record(current_user.role, record.date):
                db.session.delete(record)
                db.session.commit()
                log_activity(current_user.id, 'delete', f"حذف مرتجع {record.party_name}")
                flash('تم حذف المرتجع بنجاح', 'success')
            else:
                flash('غير مصرح لك بالحذف', 'danger')
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
                log_activity(current_user.id, 'edit', f"تعديل مرتجع {record.party_name}")
                flash('تم تحديث المرتجع بنجاح', 'success')
            else:
                flash('غير مصرح لك بالتعديل أو انتهت صلاحية التعديل', 'danger')
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
        log_activity(current_user.id, 'create', f"إضافة مرتجع {party_name}")
        row_data = [record_date.strftime('%Y-%m-%d'), return_type, party_name, product_type, product_size, product_spec, quantity, reason, current_user.full_name]
        excel_path = add_row_to_excel('يوميات المحل.xlsx', ['التاريخ', 'النوع', 'الطرف', 'الصنف', 'المقاس', 'المواصفات', 'الكمية', 'السبب', 'المسؤول'], row_data)
        if excel_path: drive_service.upload_file(excel_path, 'يوميات المحل.xlsx')
        flash('تم تسجيل المرتجع بنجاح', 'success')
        return redirect(url_for('store_returns'))
    returns = StoreReturn.query.order_by(StoreReturn.date.asc(), StoreReturn.id.asc()).all()
    return render_template('store/returns.html', returns=returns)

@app.route('/store/diary', methods=['GET', 'POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab', 'ahmed')
def store_diary():
    if request.method == 'POST':
        if request.form.get('delete_id'):
            record_id = int(request.form.get('delete_id'))
            record = StoreDiary.query.get_or_404(record_id)
            if can_delete_record(current_user.role, record.date):
                db.session.delete(record)
                db.session.commit()
                log_activity(current_user.id, 'delete', f"حذف يومية محل")
                flash('تم حذف اليومية بنجاح', 'success')
            else:
                flash('غير مصرح لك بالحذف', 'danger')
            return redirect(url_for('store_diary'))
        if request.form.get('edit_id'):
            record_id = int(request.form.get('edit_id'))
            record = StoreDiary.query.get_or_404(record_id)
            if can_edit(current_user.role, record.date, record.created_by, current_user.id):
                record.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
                record.description = request.form.get('description')
                record.amount = float(request.form.get('amount', 0))
                db.session.commit()
                log_activity(current_user.id, 'edit', f"تعديل يومية محل")
                flash('تم تحديث اليومية بنجاح', 'success')
            else:
                flash('غير مصرح لك بالتعديل أو انتهت صلاحية التعديل', 'danger')
            return redirect(url_for('store_diary'))
        record_date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        description = request.form.get('description')
        amount = float(request.form.get('amount', 0))
        new_record = StoreDiary(date=record_date, description=description, amount=amount,
                                created_by=current_user.id, created_at=datetime.utcnow())
        db.session.add(new_record)
        db.session.commit()
        log_activity(current_user.id, 'create', f"إضافة يومية محل: {description[:50]}")
        row_data = [record_date.strftime('%Y-%m-%d'), description, amount, current_user.full_name]
        excel_path = add_row_to_excel('يوميات المحل.xlsx', ['التاريخ', 'الوصف', 'المبلغ', 'المسؤول'], row_data)
        if excel_path: drive_service.upload_file(excel_path, 'يوميات المحل.xlsx')
        flash('تم تسجيل اليومية بنجاح', 'success')
        return redirect(url_for('store_diary'))
    diary = StoreDiary.query.order_by(StoreDiary.date.asc(), StoreDiary.id.asc()).all()
    return render_template('store/diary.html', diary=diary)

# ==================== الخزينة ====================
@app.route('/treasury')
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'ahmed', 'eid', 'abdo')
def treasury_index():
    if current_user.role in ['meg', 'admin', 'mariam']:
        persons = ['الحاج أحمد', 'عيد', 'عبدالله', 'الحاج فتحي']
        for person in persons:
            for acc_type in ['كاش', 'فودافون كاش', 'انستا باي', 'شيك']:
                get_or_create_treasury_account(person, acc_type)
    else:
        person_name = current_user.full_name
        for acc_type in ['كاش', 'فودافون كاش', 'انستا باي', 'شيك']:
            get_or_create_treasury_account(person_name, acc_type)

    accounts = get_visible_accounts_for_current_user()
    if current_user.role in ['meg', 'admin', 'mariam']:
        transactions = TreasuryTransaction.query.order_by(TreasuryTransaction.date.asc(), TreasuryTransaction.id.asc()).limit(50).all()
    else:
        transactions = TreasuryTransaction.query.filter_by(created_by=current_user.id).order_by(TreasuryTransaction.date.asc(), TreasuryTransaction.id.asc()).limit(50).all()

    return render_template('treasury/index.html', accounts=accounts, transactions=transactions)

@app.route('/treasury/transactions', methods=['GET', 'POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'ahmed', 'eid', 'abdo')
def treasury_transactions():
    if current_user.role in ['meg', 'admin', 'mariam']:
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
            if current_user.role in ['meg', 'admin', 'mariam']:
                account = TreasuryAccount.query.get(record.account_id)
                if account:
                    if record.transaction_type == 'deposit':
                        account.balance -= record.amount
                    else:
                        account.balance += record.amount
                db.session.delete(record)
                db.session.commit()
                log_activity(current_user.id, 'delete', f"حذف حركة خزينة {record.amount}")
                flash('تم حذف الحركة بنجاح', 'success')
            else:
                flash('غير مصرح لك بالحذف', 'danger')
            return redirect(url_for('financial_transactions'))

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
                log_activity(current_user.id, 'edit', f"تعديل حركة خزينة {record.amount}")
                flash('تم تحديث الحركة بنجاح', 'success')
            else:
                flash('غير مصرح لك بالتعديل أو انتهت صلاحية التعديل', 'danger')
            # ✅ الرجوع لصفحة المعاملات المالية مع cache buster
            return redirect(url_for('financial_transactions') + '?refresh=' + str(datetime.now().timestamp()))

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
        log_activity(current_user.id, 'create', f"إضافة حركة خزينة {transaction_type} {amount}")
        flash('تم تسجيل الحركة بنجاح', 'success')
        return redirect(url_for('treasury_transactions'))

    accounts = get_visible_accounts_for_current_user()
    if current_user.role in ['meg', 'admin', 'mariam']:
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

# ==================== باقي الملف نفس ما هو بدون تغيير ====================
# [باقي الأكواد زي ما هي من عند treasury_transfers لحد الآخر]

@app.route('/treasury/transfers', methods=['GET', 'POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam')
def treasury_transfers():
    if request.method == 'POST':
        if request.form.get('delete_id'):
            record_id = int(request.form.get('delete_id'))
            record = TreasuryTransfer.query.get_or_404(record_id)
            if current_user.role in ['meg', 'admin', 'mariam']:
                db.session.delete(record)
                db.session.commit()
                log_activity(current_user.id, 'delete', f"حذف تحويل {record.amount}")
                flash('تم حذف التحويل بنجاح', 'success')
            else:
                flash('غير مصرح لك بالحذف', 'danger')
            return redirect(url_for('treasury_transfers'))
        if request.form.get('edit_id'):
            record_id = int(request.form.get('edit_id'))
            record = TreasuryTransfer.query.get_or_404(record_id)
            if current_user.role in ['meg', 'admin', 'mariam']:
                record.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
                record.from_person = request.form.get('from_person')
                record.to_person = request.form.get('to_person')
                record.amount = float(request.form.get('amount', 0))
                record.payment_method = request.form.get('payment_method')
                record.notes = request.form.get('notes')
                db.session.commit()
                log_activity(current_user.id, 'edit', f"تعديل تحويل {record.amount}")
                flash('تم تحديث التحويل بنجاح', 'success')
            else:
                flash('غير مصرح لك بالتعديل', 'danger')
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
        log_activity(current_user.id, 'create', f"إضافة تحويلات من {from_person}")
        flash('تم تسجيل التحويلات بنجاح', 'success')
        return redirect(url_for('treasury_transfers'))

    transfers = TreasuryTransfer.query.order_by(TreasuryTransfer.date.asc(), TreasuryTransfer.id.asc()).all()
    return render_template('treasury/transfers.html', transfers=transfers)

@app.route('/treasury/accounts', methods=['GET', 'POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam')
def treasury_accounts():
    if request.method == 'POST':
        if request.form.get('delete_id'):
            account_id = int(request.form.get('delete_id'))
            account = TreasuryAccount.query.get_or_404(account_id)
            if current_user.role in ['meg', 'admin', 'mariam']:
                if account.transactions:
                    flash('لا يمكن حذف حساب له معاملات', 'danger')
                else:
                    db.session.delete(account)
                    db.session.commit()
                    log_activity(current_user.id, 'delete', f"حذف حساب خزينة {account.person_name}")
                    flash('تم حذف الحساب', 'success')
            else:
                flash('غير مصرح لك بالحذف', 'danger')
            return redirect(url_for('treasury_accounts'))
        if request.form.get('edit_id'):
            account_id = int(request.form.get('edit_id'))
            account = TreasuryAccount.query.get_or_404(account_id)
            if current_user.role in ['meg', 'admin', 'mariam']:
                account.person_name = request.form.get('person_name')
                account.account_type = request.form.get('account_type')
                account.balance = float(request.form.get('balance', 0))
                db.session.commit()
                log_activity(current_user.id, 'edit', f"تعديل حساب خزينة {account.person_name}")
                flash('تم تحديث الحساب', 'success')
            else:
                flash('غير مصرح لك بالتعديل', 'danger')
            return redirect(url_for('treasury_accounts'))
        person_name = request.form.get('person_name')
        account_type = request.form.get('account_type')
        balance = float(request.form.get('balance', 0))
        new_account = TreasuryAccount(person_name=person_name, account_type=account_type, balance=balance)
        db.session.add(new_account)
        db.session.commit()
        log_activity(current_user.id, 'create', f"إضافة حساب خزينة {person_name} {account_type}")
        flash('تم إضافة الحساب', 'success')
        return redirect(url_for('treasury_accounts'))

    accounts = TreasuryAccount.query.order_by(TreasuryAccount.person_name.asc(), TreasuryAccount.account_type.asc()).all()
    return render_template('treasury/accounts.html', accounts=accounts)

@app.route('/financial-transactions', methods=['GET', 'POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab', 'ahmed', 'eid', 'abdo')
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
                    elif txn_type == 'transfer_customer_supplier':
                        if not Customer.query.filter_by(name=new_from_party).first():
                            db.session.add(Customer(name=new_from_party))
                    from_party = new_from_party

                if to_party == 'new' and new_to_party:
                    if txn_type == 'withdrawal':
                        if not Supplier.query.filter_by(name=new_to_party).first():
                            db.session.add(Supplier(name=new_to_party))
                    elif txn_type == 'transfer_customer_supplier':
                        if not Supplier.query.filter_by(name=new_to_party).first():
                            db.session.add(Supplier(name=new_to_party))
                    to_party = new_to_party

                account = None
                if txn_type == 'deposit':
                    account_name = current_user.full_name
                    account = TreasuryAccount.query.filter_by(
                        person_name=account_name, 
                        account_type=payment_method
                    ).first()
                    if not account:
                        account = TreasuryAccount(
                            person_name=account_name, 
                            account_type=payment_method, 
                            balance=0
                        )
                        db.session.add(account)
                    account.balance += amount
                    source = from_party
                    txn_type_db = 'deposit'

                elif txn_type == 'withdrawal':
                    account_name = current_user.full_name
                    account = TreasuryAccount.query.filter_by(
                        person_name=account_name, 
                        account_type=payment_method
                    ).first()
                    if not account:
                        account = TreasuryAccount(
                            person_name=account_name, 
                            account_type=payment_method, 
                            balance=0
                        )
                        db.session.add(account)
                    account.balance -= amount
                    source = to_party
                    txn_type_db = 'withdrawal'

                elif txn_type == 'transfer_customer_supplier':
                    account = TreasuryAccount.query.filter_by(
                        person_name='تحويلات العملاء', 
                        account_type='تحويل'
                    ).first()
                    if not account:
                        account = TreasuryAccount(
                            person_name='تحويلات العملاء', 
                            account_type='تحويل', 
                            balance=0
                        )
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
                print(f"❌ Error adding financial transaction: {e}")
                flash(f'خطأ في إضافة المعاملة: {str(e)}', 'danger')
                continue

        db.session.commit()
        flash('✅ تم تسجيل المعاملات المالية بنجاح', 'success')
        return redirect(url_for('financial_transactions'))

    transactions = TreasuryTransaction.query.order_by(
        TreasuryTransaction.date.asc(), 
        TreasuryTransaction.id.asc()
    ).all()
    accounts = TreasuryAccount.query.all()
    customers = Customer.query.order_by(Customer.name.asc()).all()
    suppliers = Supplier.query.order_by(Supplier.name.asc()).all()
    
    return render_template('reports/financial.html',
                           transactions=transactions,
                           accounts=accounts,
                           customers=customers,
                           suppliers=suppliers)

# ==================== باقي الملف من غير أي تغيير ====================
# [كل الأكواد من admin_activity لحد آخر الملف زي ما هي]

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
