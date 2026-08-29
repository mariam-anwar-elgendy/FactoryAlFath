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
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-me')
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = '/tmp/flask_session'
app.config['SESSION_PERMANENT'] = True
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False

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

def init_db():
    with app.app_context():
        db.create_all()
        # إضافة أعمدة جديدة بأمان
        try:
            db.session.execute(db.text('ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR(20)'))
            db.session.execute(db.text('ALTER TABLE users ADD COLUMN IF NOT EXISTS last_activity TIMESTAMP'))
            db.session.commit()
        except:
            pass

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

        # إنشاء حسابات الخزينة للأشخاص المحددين
        treasury_persons = ['الحاج أحمد', 'عيد', 'عبدالله', 'الحاج فتحي']
        account_types = ['كاش', 'فودافون كاش', 'انستا باي']
        for person in treasury_persons:
            for acc_type in account_types:
                get_or_create_treasury_account(person, acc_type)

init_db()

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

@app.context_processor
def inject_globals():
    unread_notifications = 0
    if current_user.is_authenticated:
        unread_notifications = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    return {'now': datetime.now(), 'unread_notifications': unread_notifications}

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
    stats = {
        'raw_materials_count': FactoryRawMaterial.query.count() if current_user.role in ['meg','admin','mariam','rehab','mohamed'] else 0,
        'production_count': FactoryProduction.query.count() if current_user.role in ['meg','admin','mariam','rehab','mohamed'] else 0,
        'sales_count': StoreSale.query.count() if current_user.role in ['meg','admin','mariam','rehab','ahmed'] else 0,
        'purchases_count': StorePurchase.query.count() if current_user.role in ['meg','admin','mariam','rehab','ahmed'] else 0,
        'customers_count': Customer.query.count() if current_user.role in ['meg','admin','mariam','rehab','ahmed'] else 0,
        'suppliers_count': Supplier.query.count() if current_user.role in ['meg','admin','mariam','rehab','ahmed'] else 0,
        'treasury_balance': 0,
        'today_sales': db.session.query(db.func.sum(StoreSaleItem.total)).join(StoreSale).filter(StoreSale.date == date.today()).scalar() or 0,
        'today_purchases': db.session.query(db.func.sum(StorePurchaseItem.total)).join(StorePurchase).filter(StorePurchase.date == date.today()).scalar() or 0,
        'low_inventory_count': StoreInventory.query.filter(StoreInventory.current_quantity <= StoreInventory.min_quantity).count() if current_user.role in ['meg','admin','mariam','rehab','ahmed'] else 0,
    }

    if current_user.role in ['meg', 'admin', 'mariam']:
        stats['treasury_balance'] = db.session.query(db.func.sum(TreasuryAccount.balance)).scalar() or 0
    elif current_user.role in ['ahmed', 'eid', 'abdo']:
        stats['treasury_balance'] = db.session.query(db.func.sum(TreasuryAccount.balance)).filter(TreasuryAccount.person_name == current_user.full_name).scalar() or 0
    else:
        stats['treasury_balance'] = 0

    if current_user.role in ['meg', 'admin', 'mariam', 'rehab', 'mohamed', 'ahmed']:
        recent_sales = StoreSale.query.order_by(StoreSale.date.desc()).limit(5).all()
        recent_production = FactoryProduction.query.order_by(FactoryProduction.date.desc()).limit(5).all()
        if current_user.role in ['meg', 'admin', 'mariam']:
            recent_transactions = TreasuryTransaction.query.order_by(TreasuryTransaction.date.desc()).limit(5).all()
        else:
            recent_transactions = TreasuryTransaction.query.filter_by(created_by=current_user.id).order_by(TreasuryTransaction.date.desc()).limit(5).all()
    else:
        recent_sales = []
        recent_production = []
        recent_transactions = TreasuryTransaction.query.filter_by(created_by=current_user.id).order_by(TreasuryTransaction.date.desc()).limit(5).all()

    inactive_users_count = 0
    if current_user.role == 'admin':
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
            if current_user.role in ['meg', 'admin']:
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
    return render_template('factory/raw_materials.html', materials=materials)

@app.route('/factory/production', methods=['GET', 'POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab', 'mohamed')
def factory_production():
    if request.method == 'POST':
        if request.form.get('delete_id'):
            record_id = int(request.form.get('delete_id'))
            record = FactoryProduction.query.get_or_404(record_id)
            if current_user.role in ['meg', 'admin']:
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
            if current_user.role in ['meg', 'admin']:
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
        description = request.form.get('description')
        amount = float(request.form.get('amount', 0))
        new_record = FactoryDiary(date=record_date, description=description, amount=amount,
                                  created_by=current_user.id, created_at=datetime.utcnow())
        db.session.add(new_record)
        db.session.commit()
        log_activity(current_user.id, 'create', f"إضافة يومية مصنع: {description[:50]}")
        row_data = [record_date.strftime('%Y-%m-%d'), description, amount, current_user.full_name]
        excel_path = add_row_to_excel('يوميات المصنع.xlsx', ['التاريخ', 'الوصف', 'المبلغ', 'المسؤول'], row_data)
        if excel_path: drive_service.upload_file(excel_path, 'يوميات المصنع.xlsx')
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

@app.route('/store/transactions', methods=['GET', 'POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab', 'ahmed')
def store_transactions():
    if request.method == 'POST':
        # حذف
        if request.form.get('delete_id'):
            record_id = int(request.form.get('delete_id'))
            transaction_type = request.form.get('transaction_type')
            if current_user.role in ['meg', 'admin']:
                if transaction_type == 'sale':
                    record = StoreSale.query.get_or_404(record_id)
                    for item in record.items:
                        inv = StoreInventory.query.filter_by(product_type=item.product_type,
                                                             product_size=item.product_size,
                                                             product_spec=item.product_spec).first()
                        if inv:
                            inv.current_quantity += item.quantity
                            db.session.commit()
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
                            db.session.commit()
                    db.session.delete(record)
                    db.session.commit()
                    log_activity(current_user.id, 'delete', f"حذف شراء {record.supplier_name}")
                flash('تم الحذف بنجاح', 'success')
            else:
                flash('غير مصرح لك بالحذف', 'danger')
            return redirect(url_for('store_transactions'))

        # تعديل (سنكتفي بتعديل التاريخ والطرف)
        if request.form.get('edit_id'):
            record_id = int(request.form.get('edit_id'))
            transaction_type = request.form.get('transaction_type')
            if transaction_type == 'sale':
                record = StoreSale.query.get_or_404(record_id)
                if can_edit(current_user.role, record.date, record.created_by, current_user.id):
                    record.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
                    record.customer_name = request.form.get('party_name')
                    record.customer_phone = request.form.get('party_phone')
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
                    db.session.commit()
                    log_activity(current_user.id, 'edit', f"تعديل شراء {record.supplier_name}")
                    flash('تم تعديل الشراء بنجاح', 'success')
                else:
                    flash('غير مصرح لك بالتعديل', 'danger')
            return redirect(url_for('store_transactions'))

        # إضافة جديدة
        transaction_type = request.form.get('transaction_type')
        record_date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        party_name = request.form.get('party_name')
        party_phone = request.form.get('party_phone')
        payment_type = request.form.get('payment_type', 'آجل')

        # استقبال البنود
        product_types = request.form.getlist('product_type[]')
        product_sizes = request.form.getlist('product_size[]')
        product_specs = request.form.getlist('product_spec[]')
        quantities = request.form.getlist('quantity[]')
        unit_prices = request.form.getlist('unit_price[]')

        if transaction_type == 'sale':
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
            db.session.commit()

            for i in range(len(product_types)):
                if product_types[i].strip():
                    item = StoreSaleItem(
                        sale_id=new_sale.id,
                        product_type=product_types[i],
                        product_size=product_sizes[i] if i < len(product_sizes) else '',
                        product_spec=product_specs[i] if i < len(product_specs) else '',
                        quantity=float(quantities[i] if i < len(quantities) else 0),
                        unit_price=float(unit_prices[i] if i < len(unit_prices) else 0) if unit_prices[i] else 0,
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
            total = sum(item.total for item in new_sale.items)
            db.session.add(StoreDiary(date=record_date,
                                      description=f"بيع إلى {party_name} بقيمة {total}",
                                      amount=total,
                                      created_by=current_user.id,
                                      created_at=datetime.utcnow()))
            db.session.commit()
            log_activity(current_user.id, 'create', f"إضافة بيع لـ {party_name}")
            flash('تم تسجيل البيع بنجاح', 'success')
        else:  # purchase
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
            db.session.commit()

            for i in range(len(product_types)):
                if product_types[i].strip():
                    item = StorePurchaseItem(
                        purchase_id=new_purchase.id,
                        product_type=product_types[i],
                        product_size=product_sizes[i] if i < len(product_sizes) else '',
                        product_spec=product_specs[i] if i < len(product_specs) else '',
                        quantity=float(quantities[i] if i < len(quantities) else 0),
                        unit_price=float(unit_prices[i] if i < len(unit_prices) else 0) if unit_prices[i] else 0,
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
            total = sum(item.total for item in new_purchase.items)
            db.session.add(StoreDiary(date=record_date,
                                      description=f"شراء من {party_name} بقيمة {total}",
                                      amount=total,
                                      created_by=current_user.id,
                                      created_at=datetime.utcnow()))
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
            if current_user.role in ['meg', 'admin']:
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
            if current_user.role in ['meg', 'admin']:
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
            if current_user.role in ['meg', 'admin']:
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
            for acc_type in ['كاش', 'فودافون كاش', 'انستا باي']:
                get_or_create_treasury_account(person, acc_type)
    else:
        person_name = current_user.full_name
        for acc_type in ['كاش', 'فودافون كاش', 'انستا باي']:
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
            for acc_type in ['كاش', 'فودافون كاش', 'انستا باي']:
                get_or_create_treasury_account(person, acc_type)
    else:
        person_name = current_user.full_name
        for acc_type in ['كاش', 'فودافون كاش', 'انستا باي']:
            get_or_create_treasury_account(person_name, acc_type)

    if request.method == 'POST':
        if request.form.get('delete_id'):
            record_id = int(request.form.get('delete_id'))
            record = TreasuryTransaction.query.get_or_404(record_id)
            if current_user.role in ['meg', 'admin']:
                account = TreasuryAccount.query.get(record.account_id)
                if account:
                    if record.transaction_type == 'deposit':
                        account.balance -= record.amount
                    else:
                        account.balance += record.amount
                    db.session.commit()
                db.session.delete(record)
                db.session.commit()
                log_activity(current_user.id, 'delete', f"حذف حركة خزينة {record.amount}")
                flash('تم حذف الحركة بنجاح', 'success')
            else:
                flash('غير مصرح لك بالحذف', 'danger')
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
                    db.session.commit()

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
                db.session.commit()
                log_activity(current_user.id, 'edit', f"تعديل حركة خزينة {record.amount}")
                flash('تم تحديث الحركة بنجاح', 'success')
            else:
                flash('غير مصرح لك بالتعديل أو انتهت صلاحية التعديل', 'danger')
            return redirect(url_for('treasury_transactions'))

        # إضافة عادية
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
            db.session.commit()

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

@app.route('/treasury/transfers', methods=['GET', 'POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam')
def treasury_transfers():
    if request.method == 'POST':
        if request.form.get('delete_id'):
            record_id = int(request.form.get('delete_id'))
            record = TreasuryTransfer.query.get_or_404(record_id)
            if current_user.role in ['meg', 'admin']:
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

        # إضافة تحويل متعدد المستلمين
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

# ==================== إدارة حسابات الخزينة ====================
@app.route('/treasury/accounts', methods=['GET', 'POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam')
def treasury_accounts():
    if request.method == 'POST':
        if request.form.get('delete_id'):
            account_id = int(request.form.get('delete_id'))
            account = TreasuryAccount.query.get_or_404(account_id)
            if account.transactions:
                flash('لا يمكن حذف حساب له معاملات', 'danger')
            else:
                db.session.delete(account)
                db.session.commit()
                log_activity(current_user.id, 'delete', f"حذف حساب خزينة {account.person_name}")
                flash('تم حذف الحساب', 'success')
            return redirect(url_for('treasury_accounts'))
        if request.form.get('edit_id'):
            account_id = int(request.form.get('edit_id'))
            account = TreasuryAccount.query.get_or_404(account_id)
            account.person_name = request.form.get('person_name')
            account.account_type = request.form.get('account_type')
            account.balance = float(request.form.get('balance', 0))
            db.session.commit()
            log_activity(current_user.id, 'edit', f"تعديل حساب خزينة {account.person_name}")
            flash('تم تحديث الحساب', 'success')
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

# ==================== المعاملات المالية ====================
@app.route('/financial-transactions')
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab', 'ahmed', 'eid', 'abdo')
def financial_transactions():
    transactions = TreasuryTransaction.query.order_by(TreasuryTransaction.date.asc(), TreasuryTransaction.id.asc()).all()
    accounts = TreasuryAccount.query.all()
    customers = Customer.query.order_by(Customer.name.asc()).all()
    suppliers = Supplier.query.order_by(Supplier.name.asc()).all()
    return render_template('reports/financial.html',
                           transactions=transactions,
                           accounts=accounts,
                           customers=customers,
                           suppliers=suppliers)

# ==================== سجل النشاط ====================
@app.route('/admin/activity')
@custom_login_required
@role_required('meg', 'admin')
def admin_activity():
    activities = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).limit(200).all()
    inactive_users = []
    threshold = datetime.utcnow() - timedelta(days=3)
    all_users = User.query.filter_by(is_hidden=False).all()
    for user in all_users:
        if user.last_activity and user.last_activity < threshold:
            inactive_users.append(user)
    return render_template('admin/activity.html', activities=activities, inactive_users=inactive_users)

# ==================== التقارير ====================
@app.route('/reports')
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab')
def reports_index():
    return render_template('reports/index.html')

@app.route('/reports/daily')
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab', 'mohamed', 'ahmed')
def reports_daily():
    today = date.today()
    return render_template('reports/daily.html', today=today)

@app.route('/reports/weekly')
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab')
def reports_weekly():
    week_start = date.today() - timedelta(days=7)
    return render_template('reports/weekly.html', week_start=week_start)

@app.route('/reports/monthly')
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab')
def reports_monthly():
    month_start = date.today().replace(day=1)
    return render_template('reports/monthly.html', month_start=month_start)

@app.route('/reports/customers')
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab')
def reports_customers():
    customers = Customer.query.order_by(Customer.name.asc()).all()
    return render_template('reports/customers.html', customers=customers)

@app.route('/reports/customers/<int:customer_id>')
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab')
def report_single_customer(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    sales = StoreSale.query.filter_by(customer_name=customer.name).order_by(StoreSale.date.asc(), StoreSale.id.asc()).all()
    total_purchases = sum(s.total for s in sales)
    total_paid = sum(s.paid_amount for s in sales)
    total_remaining = total_purchases - total_paid
    return render_template('reports/customer_detail.html',
                           customer=customer,
                           sales=sales,
                           total_purchases=total_purchases,
                           total_paid=total_paid,
                           total_remaining=total_remaining)

@app.route('/reports/suppliers')
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab')
def reports_suppliers():
    suppliers = Supplier.query.order_by(Supplier.name.asc()).all()
    return render_template('reports/suppliers.html', suppliers=suppliers)

@app.route('/reports/suppliers/<int:supplier_id>')
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab')
def report_single_supplier(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)
    purchases = StorePurchase.query.filter_by(supplier_name=supplier.name).order_by(StorePurchase.date.asc(), StorePurchase.id.asc()).all()
    total_purchases = sum(p.total for p in purchases)
    total_paid = sum(p.paid_amount for p in purchases)
    total_remaining = total_purchases - total_paid
    return render_template('reports/supplier_detail.html',
                           supplier=supplier,
                           purchases=purchases,
                           total_purchases=total_purchases,
                           total_paid=total_paid,
                           total_remaining=total_remaining)

@app.route('/reports/generate-word/<report_type>/<period>')
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab')
def generate_word_report_route(report_type, period):
    try:
        today = date.today()
        company_name = "شركة الفتح"
        if report_type == 'factory':
            report_title = "تقرير يوميات المصنع"
            headers = ['التاريخ', 'الوصف', 'المقاس', 'السماكة', 'الكمية', 'المسؤول']
            data = []
            records = FactoryDiary.query.order_by(FactoryDiary.date.asc()).limit(100).all()
            for r in records:
                data.append([r.date.strftime('%Y-%m-%d'), r.description, '', '', r.amount, ''])
        elif report_type == 'store':
            report_title = "تقرير يوميات المحل"
            headers = ['التاريخ', 'النوع', 'الطرف', 'الصنف', 'الكمية', 'الإجمالي']
            data = []
            sales = StoreSale.query.order_by(StoreSale.date.asc()).limit(50).all()
            for s in sales:
                data.append([s.date.strftime('%Y-%m-%d'), 'بيع', s.customer_name, s.product_type, s.quantity, s.total])
        elif report_type == 'treasury':
            report_title = "تقرير الخزينة"
            headers = ['التاريخ', 'الشخص', 'النوع', 'المبلغ', 'طريقة الدفع']
            data = []
            transactions = TreasuryTransaction.query.order_by(TreasuryTransaction.date.asc()).limit(100).all()
            for t in transactions:
                account = TreasuryAccount.query.get(t.account_id)
                data.append([t.date.strftime('%Y-%m-%d'), account.person_name if account else '', t.transaction_type, t.amount, t.payment_method])
        else:
            flash('نوع التقرير غير معروف', 'danger')
            return redirect(url_for('dashboard'))

        period_names = {'daily': 'يومي', 'weekly': 'أسبوعي', 'monthly': 'شهري', 'custom': 'مخصص'}
        period_name = period_names.get(period, period)

        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'word_reports')
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, f"{report_type}_{period}_{today.strftime('%Y%m%d')}.docx")

        generate_word_report(
            company_name=company_name,
            report_title=report_title,
            report_date=today.strftime('%Y-%m-%d'),
            period=period_name,
            table_headers=headers,
            table_data=data,
            output_path=output_file
        )

        return send_file(output_file, as_attachment=True)
    except Exception as e:
        flash(f'خطأ في توليد التقرير: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/reports/download-excel/<file_name>')
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab')
def download_excel(file_name):
    file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'excel_files', file_name)
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    flash('الملف غير موجود', 'danger')
    return redirect(url_for('dashboard'))

# ==================== الإدارة ====================
@app.route('/admin/users')
@custom_login_required
@role_required('meg', 'admin')
def admin_users():
    users = User.query.filter_by(is_hidden=False).all() if current_user.role != 'meg' else User.query.all()
    return render_template('admin/users.html', users=users)

@app.route('/admin/users/add', methods=['GET', 'POST'])
@custom_login_required
@role_required('meg', 'admin')
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
@role_required('meg', 'admin')
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

@app.route('/admin/categories')
@custom_login_required
@role_required('meg', 'admin', 'mariam')
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
@role_required('meg', 'admin', 'mariam')
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
@role_required('meg', 'admin', 'mariam')
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
@role_required('meg', 'admin')
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
