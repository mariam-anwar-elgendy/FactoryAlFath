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
from models import AlMasaCrane, AlMasaPartner, AlMasaOperation, AlMasaCheck, AlMasaExpense
from utils import (
    login_required as custom_login_required,
    role_required,
    can_edit,
    add_row_to_excel,
    generate_word_report,
    GoogleDriveService
)

app = Flask(__name__)

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-me')
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = '/tmp/flask_session'
app.config['SESSION_PERMANENT'] = True
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

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

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'يرجى تسجيل الدخول أولاً'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

drive_service = GoogleDriveService(
    credentials_file=os.environ.get('GOOGLE_CREDENTIALS_FILE', 'client_secrets.json'),
    folder_id=os.environ.get('GOOGLE_DRIVE_FOLDER_ID', '')
)

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

def init_db():
    with app.app_context():
        db.create_all()
        try:
            db.session.execute(db.text('ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR(20)'))
            db.session.execute(db.text('ALTER TABLE users ADD COLUMN IF NOT EXISTS last_activity TIMESTAMP'))
            db.session.commit()
        except:
            pass
        
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
            {'username': 'sayed',
             'password': 'sayed1977#',
             'full_name': 'سيد',
             'role': 'sayed',
             'is_hidden': False},
            {'username': 'dina',
             'password': 'dina2003',
             'full_name': 'دينا',
             'role': 'dina',
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
        if current_user.role == 'sayed':
            return redirect(url_for('choose_company'))
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.role == 'sayed':
            return redirect(url_for('choose_company'))
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
            if user.role == 'sayed':
                return redirect(url_for('choose_company'))
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
    if current_user.role == 'sayed':
        return redirect(url_for('choose_company'))
    role = current_user.role
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
    elif role == 'dina':
        return redirect(url_for('almasa_index'))
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
        
        if supplier and not Supplier.query.filter_by(name=supplier).first():
            db.session.add(Supplier(name=supplier))
        
        new_record = FactoryRawMaterial(date=record_date, pipe_size=pipe_size, pipe_thickness=pipe_thickness,
                                        quantity=quantity, supplier=supplier, notes=notes,
                                        created_by=current_user.id, created_at=datetime.utcnow())
        db.session.add(new_record)
        db.session.commit()
        log_activity(current_user.id, 'create', f"إضافة وارد ماسورة {pipe_size} {pipe_thickness} كمية {quantity}")
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

@app.route('/store')
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab', 'ahmed', 'sayed')
def store_index():
    today = date.today()
    sales = StoreSale.query.filter_by(date=today).order_by(StoreSale.id.asc()).all()
    purchases = StorePurchase.query.filter_by(date=today).order_by(StorePurchase.id.asc()).all()
    receiving = StoreReceiving.query.filter_by(date=today).order_by(StoreReceiving.id.asc()).all()
    return render_template('store/index.html', sales=sales, purchases=purchases, receiving=receiving)

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

        else:
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
                log_activity(current_user.id, 'delete', f"حذف تحويل {record.amount}")
                flash('تم حذف التحويل بنجاح', 'success')
            else:
                flash('غير مصرح لك بالحذف', 'danger')
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
                    log_activity(current_user.id, 'delete', f"حذف حساب خزينة {account.person_name}")
                    flash('تم حذف الحساب', 'success')
            else:
                flash('غير مصرح لك بالحذف', 'danger')
            return redirect(url_for('treasury_accounts'))
        if request.form.get('edit_id'):
            account_id = int(request.form.get('edit_id'))
            account = TreasuryAccount.query.get_or_404(account_id)
            if current_user.role in ['meg', 'admin', 'mariam', 'sayed']:
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
                    elif txn_type == 'transfer_customer_supplier':
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
                    elif txn_type == 'transfer_customer_supplier':
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

# ==================== شركة الماسة ====================
@app.route('/almasa')
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_index():
    cranes = AlMasaCrane.query.order_by(AlMasaCrane.id.asc()).all()
    return render_template('almasa/index.html', cranes=cranes)

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
        
        new_crane = AlMasaCrane(name=name, notes=notes)
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
    
    cranes = AlMasaCrane.query.order_by(AlMasaCrane.id.asc()).all()
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
        crane_id=crane_id,
        start_date=start_date,
        end_date=end_date,
        actual_daily_value=actual_daily,
        default_daily_value=default_daily,
        days_count=days_count,
        actual_total=actual_total,
        default_total=default_total,
        created_by=current_user.id
    )
    db.session.add(operation)
    db.session.commit()
    flash('تم إضافة العملية بنجاح', 'success')
    return redirect(url_for('almasa_crane_detail', crane_id=crane_id))

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
        crane_id=crane_id,
        date=date_str,
        expense_type=expense_type,
        amount=amount,
        notes=notes,
        created_by=current_user.id
    )
    db.session.add(expense)
    db.session.commit()
    flash('تم إضافة المصروف بنجاح', 'success')
    return redirect(url_for('almasa_crane_detail', crane_id=crane_id))

@app.route('/almasa/checks/add', methods=['POST'])
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_add_check():
    crane_id = int(request.form.get('crane_id'))
    check_number = request.form.get('check_number')
    company_name = request.form.get('company_name')
    amount = float(request.form.get('amount', 0))
    due_date = datetime.strptime(request.form.get('due_date'), '%Y-%m-%d').date()
    
    check = AlMasaCheck(
        crane_id=crane_id,
        check_number=check_number,
        company_name=company_name,
        amount=amount,
        due_date=due_date,
        status='معلق'
    )
    db.session.add(check)
    db.session.commit()
    flash('تم إضافة الشيك بنجاح', 'success')
    return redirect(url_for('almasa_crane_detail', crane_id=crane_id))

@app.route('/almasa/reports')
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_reports():
    cranes = AlMasaCrane.query.all()
    return render_template('almasa/reports.html', cranes=cranes)

@app.route('/almasa/reports/crane/<int:crane_id>')
@custom_login_required
@role_required('sayed', 'dina', 'admin', 'meg')
def almasa_crane_report(crane_id):
    crane = AlMasaCrane.query.get_or_404(crane_id)
    operations = AlMasaOperation.query.filter_by(crane_id=crane_id).order_by(AlMasaOperation.start_date.asc()).all()
    checks = AlMasaCheck.query.filter_by(crane_id=crane_id).order_by(AlMasaCheck.due_date.asc()).all()
    expenses = AlMasaExpense.query.filter_by(crane_id=crane_id).order_by(AlMasaExpense.date.asc()).all()
    partners = AlMasaPartner.query.filter_by(crane_id=crane_id).all()
    
    total_expenses = sum(e.amount for e in expenses)
    total_actual = sum(o.actual_total for o in operations)
    total_default = sum(o.default_total for o in operations)
    
    actual_check_amount = total_actual + (total_actual * 0.14)
    net_actual = total_actual - (total_actual * 0.085) - total_expenses
    net_default = total_default - (total_default * 0.085) - total_expenses
    
    basic_partners_profit = (net_actual - net_default) / 2
    
    partners_profit = []
    basic_count = sum(1 for p in partners if p.is_basic)
    for p in partners:
        if p.is_basic:
            profit = basic_partners_profit / basic_count if basic_count > 0 else 0
        else:
            profit = net_default * (p.percentage / 100)
        partners_profit.append({'partner': p, 'profit': profit})
    
    return render_template('almasa/crane_report.html',
                           crane=crane,
                           operations=operations,
                           checks=checks,
                           expenses=expenses,
                           partners=partners,
                           total_expenses=total_expenses,
                           total_actual=total_actual,
                           total_default=total_default,
                           actual_check_amount=actual_check_amount,
                           net_actual=net_actual,
                           net_default=net_default,
                           basic_partners_profit=basic_partners_profit,
                           partners_profit=partners_profit)

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
                               from_date=None,
                               to_date=None,
                               report_type=report_type,
                               combined_diary=[],
                               raw_materials=[],
                               production=[],
                               sales=[],
                               purchases=[],
                               transactions=[])

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
                           from_date=from_date_str,
                           to_date=to_date_str,
                           report_type=report_type,
                           raw_materials=raw_materials,
                           production=production,
                           factory_diary=factory_diary,
                           sales=sales,
                           purchases=purchases,
                           transactions=transactions,
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
                           customer=customer,
                           sales=sales,
                           total_purchases=total_purchases,
                           total_paid=total_paid,
                           total_remaining=total_remaining,
                           treasury_txns=treasury_txns)

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
                           supplier=supplier,
                           purchases=purchases,
                           total_purchases=total_purchases,
                           total_paid=total_paid,
                           total_remaining=total_remaining,
                           treasury_txns=treasury_txns)

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
        log_activity(current_user.id, 'create', f"إضافة مستخدم {username}")
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
        log_activity(current_user.id, 'edit', f"تعديل مستخدم {user.username}")
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
    log_activity(current_user.id, 'delete', f"حذف مستخدم {user.username}")
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
                           categories=categories,
                           sizes=sizes,
                           thicknesses=thicknesses,
                           suppliers=suppliers,
                           customers=customers)

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
    log_activity(current_user.id, 'create', f"إضافة {category_type} {name}")
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
    else:
        flash('نوع غير معروف', 'danger')
        return redirect(url_for('admin_categories'))
    db.session.commit()
    log_activity(current_user.id, 'edit', f"تعديل {category_type} {new_name}")
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
    else:
        flash('نوع غير معروف', 'danger')
        return redirect(url_for('admin_categories'))
    db.session.commit()
    log_activity(current_user.id, 'delete', f"حذف {category_type} {item_id}")
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
        log_activity(current_user.id, 'edit', f"تعديل الملف الشخصي")
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
        log_activity(current_user.id, 'edit', f"تغيير كلمة المرور")
        flash('تم تغيير كلمة المرور بنجاح', 'success')
        return redirect(url_for('dashboard'))
    return render_template('settings/password.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)    
