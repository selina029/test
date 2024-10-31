from datetime import datetime, timedelta
import os
import secrets
import requests
import base64
from flask import Flask, request, render_template, redirect, url_for, session, jsonify, flash, abort, current_app
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_mail import Mail, Message
from sqlalchemy import text, Boolean, func
from sqlalchemy.exc import IntegrityError
from wtforms import StringField, PasswordField, SubmitField, DateField, FloatField, IntegerField, DecimalField, BooleanField
from wtforms.validators import DataRequired, InputRequired, Email, Length, EqualTo
from flask_wtf import FlaskForm
from itertools import groupby
from model import db, Manager, Product, ProductImage, Register, Orders, OrderDetails, CartItem, LineUser
from decimal import Decimal
from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, QuickReply, QuickReplyButton, MessageAction, ImageSendMessage, FlexSendMessage, BubbleContainer, TemplateSendMessage, ButtonsTemplate, MessageTemplateAction
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from flask import session as flask_session
from linebot import LineBotApi, WebhookParser
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from werkzeug.exceptions import BadRequest, Forbidden
from sqlalchemy.exc import SQLAlchemyError
import hashlib, re
from hashlib import sha256




# 訂單狀態代碼
ORDER_STATUS_PENDING = 1  # 待確定
ORDER_STATUS_PROCESSING = 2  # 處理中
ORDER_STATUS_COMPLETED = 3  # 已完成
ORDER_STATUS_CANCELLED = 4  # 已取消

# 付款狀態代碼
PAYMENT_STATUS_UNPAID = 1  # 未付款
PAYMENT_STATUS_PAID = 2  # 已付款
PAYMENT_STATUS_CANCELLED = 3  # 已取消
PAYMENT_STATUS_REFUNDED = 4  # 已退款

# 配送狀態代碼
DELIVERY_STATUS_PREPARING = 1  # 備貨中
DELIVERY_STATUS_PROCESSING = 2  # 處理中
DELIVERY_STATUS_SHIPPED = 3  # 已發貨
DELIVERY_STATUS_DELIVERED = 4  # 已送達
DELIVERY_STATUS_RETURNED = 5  # 已退回
DELIVERY_STATUS_CANCELLED = 6  # 已取消

# 確保你的 UPLOAD_FOLDER 和靜態路徑設定正確
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__, static_url_path='/static')
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://admin:AWMHp9gGEF8zMMq239xzMk4uG5wb1jJ2@dpg-csaitb3qf0us739v24q0-a.singapore-postgres.render.com/tea_lounge_ld58'
app.config['UPLOAD_FOLDER'] = 'static/uploads/'  # 上傳檔案的目錄
app.config['SECRET_KEY'] = secrets.token_hex(16)
app.config['SQLALCHEMY_ECHO'] = True
app.config['MAIL_SERVER'] = 'smtp.gmail.com'  # 使用 Gmail 的 SMTP 伺服器
app.config['MAIL_PORT'] = 587  # 使用 Gmail 的 SMTP 端口
app.config['MAIL_USE_TLS'] = True  # Gmail 支持 TLS 加密
app.config['MAIL_USERNAME'] = 'tealoungebarnew@gmail.com'  # 你的 Gmail 帳號
app.config['MAIL_PASSWORD'] = 'exmi itpa uoeq kcut'  # 你的 Gmail 密碼
app.config['MAIL_DEFAULT_SENDER'] = 'noreply@gmail.com'  # 默認的發件人地址
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'a_random_string_that_is_hard_to_guess')  # 設定 secret_key

# LINE OAuth2 設定
LINE_CHANNEL_ID = 'YOUR_CHANNEL_ID'
LINE_CHANNEL_SECRET = 'YOUR_CHANNEL_SECRET'
LINE_REDIRECT_URI = 'http://localhost:5000/line_callback'  # 回調網址

# Initialize extensions
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
mail = Mail(app)


line_bot_api = LineBotApi('')  
handler = WebhookHandler('')
parser = WebhookParser('')  # 初始化 parser

engine = create_engine(app.config['SQLALCHEMY_DATABASE_URI'])
Session = sessionmaker(bind=engine)

# Ensure model import is done after app is initialized
from model import db, Manager, Product, ProductImage, Register, Orders, OrderDetails, CartItem, LineUser

def hash_user_id(user_id):
    return hashlib.sha256(user_id.encode()).hexdigest()

def get_original_user_id(user_id_hash):
    for user in LineUser.query.all():
        if hashlib.sha256(user.user_id.encode()).hexdigest() == user_id_hash:
            return user.user_id
    return None

def hash_order_id(order_id):
    secret_key = "your_secret_key"
    return sha256(f"{secret_key}{order_id}".encode()).hexdigest()

# 反哈希函數，檢查哈希值是否與原始訂單編號匹配
def verify_hash_order_id(hashed_id, order_id):
    return hashed_id == hash_order_id(order_id)


class User(UserMixin):
    def __init__(self, id, name=None, phone=None, email=None):
        self.id = id
        self.name = name
        self.phone = phone
        self.email = email

    @staticmethod
    def get(id):
        return Register.query.get(id)  # 確保這裡查找的是 Register 的 ID

    def get_id(self):
        return str(self.id)  # 返回字符串形式的 id

@login_manager.user_loader
def load_user(user_id):
    # 根據 user_id 查詢 Register 模型
    user = Register.query.get(int(user_id))
    if user is None:
        return None
   
    # 創建 User 實例，並傳遞其他用戶資料（如需要）
    return User(id=user.MemberID, name=user.Name, phone=user.Phone, email=user.Email)

def send_reset_email(user):
    token = user.reset_token
    msg = Message('重設您的 Tea Lounge 密碼',
                  sender='noreply@yourdomain.com',
                  recipients=[user.Email])
    msg.body = f'''要重設您的密碼，請點擊以下連結：
{url_for('reset_password', token=token, _external=True)}

如果您沒有要求重設密碼，請忽略此郵件。
'''
    mail.send(msg)
    
def send_order_email(order, order_details):
    msg = Message('新訂單通知',
                  sender=app.config['MAIL_DEFAULT_SENDER'],
                  recipients=['tealoungebarnew@gmail.com'])
    # 渲染 HTML 模板為 email 正文
    html_body = render_template('orderDeatil_email.html', order=order, order_details=order_details)
    
    # 將渲染後的 HTML 加入 email 正文
    msg.html = html_body
    
    mail.send(msg)
        
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS  

class ProductForm(FlaskForm):
    ProductName = StringField('產品名稱', validators=[DataRequired()])
    Quantity = IntegerField('數量', validators=[DataRequired()])
    Price = DecimalField('價格', validators=[DataRequired()], places=2)
    Ingredients = StringField('成分')
    Origin = StringField('產地')
    Notes = StringField('備註')
    submit = SubmitField('提交')
    
def update_order_status(order_id, new_order_status, new_payment_status, new_delivery_status):
    try:
        order = Orders.query.get(order_id)
        if order:
            order.OrderStatusID = new_order_status
            order.PaymentStatusID = new_payment_status
            order.DeliveryStatusID = new_delivery_status
            db.session.commit()
            return True
        return False
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"更新訂單狀態時發生錯誤: {e}")
        return False

def get_product_id(product_name):
    try:
        product = Product.query.filter_by(ProductName=product_name).first()
        if product:
            return product.ProductID
        else:
            app.logger.info(f"未找到產品: {product_name}")
            return None
    except Exception as e:
        app.logger.error(f"查詢產品 ID 時發生錯誤: {e}")
        return None

def get_member_id(email):
    try:
        result = db.session.execute(text("SELECT MemberID FROM register WHERE Email = :email"), {'email': email})
        member = result.fetchone()
        return member[0] if member else None
    except Exception as e:
        print(f"查詢會員 ID 時發生錯誤: {e}")
        return None

def insert_order_details(order_id, product_name, product_image, unit_price, quantity, total_price, customer_name, customer_phone, customer_email, shipping_address, receiver_name, receiver_phone, remittance_code):
    try:
        product_id = get_product_id(product_name)
        member_id = get_member_id(customer_email)
        
        if product_id and member_id:
            order_detail = OrderDetails(
                OrderID=order_id,
                ProductID=product_id,
                ProductName=product_name,
                ProductImage=product_image,
                UnitPrice=unit_price,
                Quantity=quantity,
                TotalPrice=total_price,
                CustomerName=customer_name,
                CustomerPhone=customer_phone,
                CustomerEmail=customer_email,
                ShippingAddress=shipping_address,
                ReceiverName=receiver_name,
                ReceiverPhone=receiver_phone,
                RemittanceCode=remittance_code
            )
            db.session.add(order_detail)
            db.session.commit()
            return True
        return False
    except Exception as e:
        db.session.rollback()
        print(f"插入訂單明細時發生錯誤: {e}")
        return False
    
def get_cart_items(member_id):
    cart_items = CartItem.query.filter_by(MemberID=member_id).all()
    items = []
    for cart_item in cart_items:
        items.append({
            'product': {
                'ProductID': cart_item.product.ProductID,
                'ProductName': cart_item.product.ProductName,
                'Price': cart_item.product.Price
            },
            'quantity': cart_item.quantity
        })
    return items

def calculate_subtotal(member_id):
    cart_items = get_cart_items(member_id)  # 獲取購物車中的項目
    subtotal = sum(
        Decimal(item['product']['Price']) * item['quantity']
        for item in cart_items
    )
    return subtotal

def calculate_shipping_fee():
    # 假設運費是固定的，你可以根據需要進行調整
    return Decimal('50.00')  # 例如：固定運費50元

class RegisterForm(FlaskForm):
    name = StringField('姓名', validators=[InputRequired(), Length(max=200)])
    phone = StringField('電話', validators=[InputRequired(), Length(max=20)])
    email = StringField('電子郵件', validators=[InputRequired(), Email(), Length(max=250)])
    password = PasswordField('密碼', validators=[InputRequired(), Length(min=6)])
    pass_confirm = PasswordField('確認密碼', validators=[InputRequired(), EqualTo('password', message='密碼必須相符')])
    birthday = DateField('生日', format='%Y-%m-%d', validators=[InputRequired()])
    user_id = StringField('用戶ID', validators=[DataRequired()])  # 確保此行存在
    submit = SubmitField('註冊')

class LoginForm(FlaskForm):
    phone = StringField('電話', validators=[InputRequired(), Length(max=20)])
    password = PasswordField('密碼', validators=[InputRequired()])
    submit = SubmitField('登入')
    
@app.route('/manager')
def login_redirect():
    return redirect(url_for('manager_login'))


def upload_image_to_github(repo_owner, repo_name, file, commit_message, github_token):
    filename = secure_filename(file.filename)
    file_path = f"static/uploads/{filename}"  # 更新為 test/static/uploads

    # 編碼圖片內容為 Base64
    encoded_image = base64.b64encode(file.read()).decode('utf-8')

    api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{file_path}"

    payload = {
        "message": commit_message,
        "content": encoded_image
    }

    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json"
    }

    response = requests.put(api_url, json=payload, headers=headers)

    if response.status_code == 201:
        return True
    else:
        print(f"GitHub API error: {response.status_code} - {response.text}")
        return False

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        flash('沒有選擇檔案', 'error')
        return redirect(request.url)
    
    file = request.files['file']
    
    if file.filename == '':
        flash('沒有選擇檔案', 'error')
        return redirect(request.url)
    
    if file and allowed_file(file.filename):
        # 使用 secure_filename 確保檔名安全
        filename = secure_filename(file.filename)
        
        # 從環境變數獲取 GitHub token
        github_token = os.getenv("GITHUB_TOKEN")
        if not github_token:
            flash('GitHub token 未設定', 'error')
            return redirect(request.url)

        # 上傳檔案到 GitHub
        github_upload_success = upload_image_to_github(
            repo_owner="selina029",
            repo_name="test",
            file=file,
            commit_message=f"Upload {filename} to static/uploads folder",
            github_token=github_token
        )
        
        if github_upload_success:
            flash('檔案成功上傳到 GitHub', 'success')
            return redirect(url_for('uploaded_file', filename=filename))
        else:
            flash('檔案上傳到 GitHub 失敗', 'error')
            return redirect(request.url)
    
    flash('檔案格式不允許', 'error')
    return redirect(request.url)

# 更新的 uploaded_file route
@app.route('/uploaded/<filename>')
def uploaded_file(filename):
    # 確保檔案存在於指定路徑
    file_path = f'uploads/{filename}'
    if os.path.exists(os.path.join('static', file_path)):
        return redirect(url_for('static', filename=file_path))
    else:
        flash('檔案未找到', 'error')
        return redirect(url_for('upload'))

@app.route('/manager_login', methods=['GET', 'POST'])
def manager_login():
    if request.method == 'POST':
        try:
            data = request.get_json()
            username = data.get('username')
            password = data.get('password')
            
            manager = Manager.query.filter_by(Username=username).first()
            
            if manager and manager.check_password(password):
                session['logged_in'] = True
                session['username'] = username
                next_url = request.args.get('next')  # 確保處理 next 參數
                return redirect(next_url or url_for('orders'))
            
            return jsonify({'status': 'error', 'message': '用戶名或密碼錯誤'}), 401
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 400
    
    return render_template('login.html')

@app.route('/add_product', methods=['GET', 'POST'])
def add_product():
    if request.method == 'POST':
        try:
            name = request.form['ProductName']
            quantity = request.form['Quantity']
            price = request.form['Price']
            ingredients = request.form['Ingredients']
            origin = request.form['Origin']
            notes = request.form['Notes']
            images = request.files.getlist('images')

            # 處理數量
            quantity = process_quantity(quantity)
            if quantity is None:
                return jsonify(success=False, message='數量必須是有效的數字。')

            # 處理價格
            price = process_price(price)
            if price is None:
                return jsonify(success=False, message='價格必須是有效的數字。')

            # 檢查產品是否存在
            product_id = handle_product(name, quantity, price, ingredients, origin, notes)
            if product_id is None:
                return jsonify(success=False, message='產品新增或更新失敗。')

            # 處理產品圖片
            image_url = handle_images(images, product_id)  # 假設這個函數會返回圖片的 URL

            # 發送 LINE 通知
            send_line_notification(name, ingredients, origin, notes, image_url)

            return jsonify(success=True, message='產品已新增或更新且成功推播!')
        except Exception as e:
            return jsonify(success=False, message=f'發生錯誤: {str(e)}')

    return render_template('add_product.html')

def get_all_user_ids_from_db():
    users = LineUser.query.all()
    return [user.user_id for user in users]

def send_line_notification(name, ingredients, origin, notes, image_url):
    try:
        # 推播文字訊息
        message = (
            f"新產品已上線！\n"
            f"產品名稱: {name}\n"
            f"成分: {ingredients}\n"
            f"產地: {origin}\n"
            f"備註: {notes}"
        )
        
        # 推播訊息給所有用戶
        user_ids = get_all_user_ids_from_db()  # 從資料庫獲取所有用戶的 user_id
        for user_id in user_ids:
            try:
                # 發送文字訊息
                line_bot_api.push_message(user_id, TextSendMessage(text=message))
                
                # 發送圖片訊息
                image_message = ImageSendMessage(
                    original_content_url=image_url,
                    preview_image_url=image_url  # 預覽圖可以使用相同的圖片 URL
                )
                line_bot_api.push_message(user_id, image_message)
            except Exception as e:
                print(f'發送給 {user_id} 時發生錯誤: {e}')
                continue  # 遇到錯誤時繼續發送給其他用戶
    except Exception as e:
        flash(f'發送 Line 推播時發生錯誤: {e}', 'error')

def process_quantity(quantity):
    if quantity.strip():
        try:
            return int(quantity)
        except ValueError:
            return None
    return None

def process_price(price):
    try:
        return round(float(price), 2)
    except ValueError:
        return None

def handle_product(name, quantity, price, ingredients, origin, notes):
    try:
        existing_product = Product.query.filter_by(ProductName=name).first()
        if existing_product:
            # 更新現有產品的資料
            existing_product.Quantity = quantity
            existing_product.Price = price
            existing_product.Ingredients = ingredients
            existing_product.Origin = origin
            existing_product.Notes = notes
            db.session.commit()
            product_id = existing_product.ProductID
        else:
            # 新增新產品
            new_product = Product(
                ProductName=name, Quantity=quantity, Price=price,
                Ingredients=ingredients, Origin=origin, Notes=notes
            )
            db.session.add(new_product)
            db.session.commit()
            product_id = new_product.ProductID

        return product_id
    except Exception as e:
        db.session.rollback()
        flash(f'處理產品時發生錯誤: {e}', 'error')
        return None

def handle_images(images, product_id):
    try:
        # 刪除現有產品的舊圖片
        ProductImage.query.filter_by(ProductID=product_id).delete()

        # 保存新圖片
        for idx, image in enumerate(images):
            if image and allowed_file(image.filename):
                filename = secure_filename(image.filename)
                # 確保檔名唯一
                filename = f"{product_id}_{idx}_{filename}"
                image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                image.save(image_path)
                new_image = ProductImage(ProductID=product_id, ImagePath=filename, ImageOrder=idx)
                db.session.add(new_image)

        db.session.commit()
        
        # 假設使用第一張圖片的 URL 作為推播圖片
        if images:
            return url_for('static', filename=f'uploads/{product_id}_0_{secure_filename(images[0].filename)}')

    except Exception as e:
        db.session.rollback()
        flash(f'處理圖片時發生錯誤: {e}', 'error')
        return None

def search_orders(target, value):
    if target == 'id' and value.isdigit():
        return Orders.query.filter_by(OrderID=int(value)).all()
    elif target == 'date':
        try:
            search_date = datetime.strptime(value, '%Y-%m-%d')
            end_date = search_date + timedelta(days=1)
            return Orders.query.filter(Orders.OrderDate >= search_date,
                                       Orders.OrderDate < end_date).all()
        except ValueError:
            return []
    elif target == 'phone':
        return db.session.query(OrderDetails).filter(OrderDetails.CustomerPhone.like(f'%{value}%')).all()
    elif target == 'name':
        return Orders.query.filter(Orders.CustomerName.like(f'%{value}%')).all()
    else:
        return []

@app.route('/orders', methods=['GET', 'POST'])
def orders():
    if not session.get('logged_in'):
        return redirect(url_for('manager_login'))

    try:
        if request.method == 'POST':
            data = request.get_json()
            search_target = data.get('target')
            search_value = data.get('value')

            if search_target and search_value:
                # 根據搜尋條件查詢訂單，並按 OrderID 降序排列
                all_orders = search_orders(search_target, search_value).order_by(Orders.OrderID.desc())
            else:
                # 如果沒有搜尋條件，顯示所有訂單，並按 OrderID 降序排列
                all_orders = Orders.query.order_by(Orders.OrderID.desc()).all()
        else:
            # GET 請求時顯示所有訂單，並按 OrderID 降序排列
            all_orders = Orders.query.order_by(Orders.OrderID.desc()).all()

        # 為每個訂單生成哈希值
        for order in all_orders:
            order.hash = hash_order_id(order.OrderID)

        return render_template('orders.html', orders=all_orders)

    except Exception as e:
        print(f"Error retrieving or searching orders: {e}")
        return "An error occurred while retrieving orders.", 500



@app.route('/search_orders', methods=['POST'])
def search_orders_route():
    data = request.get_json()
    target = data.get('target')
    value = data.get('value')

    if target and value:
        if target == 'phone':
            results = db.session.query(OrderDetails).filter(OrderDetails.CustomerPhone.like(f'%{value}%')).all()
        else:
            results = search_orders(target, value)
    else:
        results = []

    def get_status_class(status_type, status_value):
        status_classes = {
            'OrderStatusID': {
                ORDER_STATUS_PENDING: 'status_pending',
                ORDER_STATUS_PROCESSING: 'status_handling',
                ORDER_STATUS_COMPLETED: 'status_complete',
                ORDER_STATUS_CANCELLED: 'status_cancel'
            },
            'PaymentStatusID': {
                PAYMENT_STATUS_UNPAID: 'status_unpaid',
                PAYMENT_STATUS_PAID: 'status_paid',
                PAYMENT_STATUS_CANCELLED: 'status_cancel',
                PAYMENT_STATUS_REFUNDED: 'status_refund'
            },
            'DeliveryStatusID': {
                DELIVERY_STATUS_PREPARING: 'status_handling',
                DELIVERY_STATUS_PROCESSING: 'status_pending',
                DELIVERY_STATUS_SHIPPED: 'status_shipped',
                DELIVERY_STATUS_DELIVERED: 'status_arrived',
                DELIVERY_STATUS_RETURNED: 'status_return',
                DELIVERY_STATUS_CANCELLED: 'status_cancel'
            }
        }
        return status_classes.get(status_type, {}).get(status_value, 'status_unknown')

    orders = [{
        'OrderID': order.OrderID,
        'OrderDate': order.OrderDate.strftime('%Y-%m-%d') if hasattr(order, 'OrderDate') else 'N/A',
        'Status': Orders.get_status_text('OrderStatusID', order.OrderStatusID) if hasattr(order, 'OrderStatusID') else 'N/A',
        'PaymentStatus': Orders.get_status_text('PaymentStatusID', order.PaymentStatusID) if hasattr(order, 'PaymentStatusID') else 'N/A',
        'DeliveryStatus': Orders.get_status_text('DeliveryStatusID', order.DeliveryStatusID) if hasattr(order, 'DeliveryStatusID') else 'N/A',
        'CustomerName': order.CustomerName,
        'TotalPrice': float(order.TotalPrice) if hasattr(order, 'TotalPrice') else 0.0,
        'StatusClass': get_status_class('OrderStatusID', order.OrderStatusID) if hasattr(order, 'OrderStatusID') else 'status_unknown',
        'PaymentStatusClass': get_status_class('PaymentStatusID', order.PaymentStatusID) if hasattr(order, 'PaymentStatusID') else 'status_unknown',
        'DeliveryStatusClass': get_status_class('DeliveryStatusID', order.DeliveryStatusID) if hasattr(order, 'DeliveryStatusID') else 'status_unknown',
        'DetailURL': url_for('orderDetail', hashed_order_id=hash_order_id(order.OrderID))  # 更新此行
    } for order in results]

    return jsonify(orders)


@app.route('/orders/<string:hashed_order_id>', methods=['GET', 'POST'])
def get_orders(hashed_order_id):
    try:
        # 從所有訂單中尋找與哈希值匹配的訂單
        orders = Orders.query.all()
        order = next((order for order in orders if verify_hash_order_id(hashed_order_id, order.OrderID)), None)

        if not order:
            print(f"No matching order found for hash: {hashed_order_id}")
            abort(404, description="Order not found")

        if request.method == 'POST':
            data = request.get_json()
            new_order_status = data.get('order_status')
            new_payment_status = data.get('payment_status')
            new_delivery_status = data.get('delivery_status')

            if update_order_status(order.OrderID, new_order_status, new_payment_status, new_delivery_status):
                return jsonify({'status': 'success'})
            else:
                print(f"Failed to update order {order.OrderID} status")
                return jsonify({'status': 'error', 'message': '更新訂單狀態失敗'}), 400

        return render_template('orders.html', order=order)
    except Exception as e:
        print(f"Error in get_orders: {e}")
        return "An error occurred while retrieving the order.", 500

@app.route('/orderDetail/<string:hashed_order_id>')
def orderDetail(hashed_order_id):
    try:
        # 從所有訂單中尋找與哈希值匹配的訂單
        orders = Orders.query.all()
        order = next((order for order in orders if verify_hash_order_id(hashed_order_id, order.OrderID)), None)

        if not order:
            print(f"No matching order found for hash: {hashed_order_id}")
            abort(404, description="Order not found")

        # 獲取訂單明細
        order_details = db.session.query(OrderDetails).filter(OrderDetails.OrderID == order.OrderID).all()

        return render_template('orderDetail.html', order=order, order_details=order_details)
    except Exception as e:
        print(f"Error in orderDetail: {e}")
        return "An error occurred while retrieving the order details.", 500


@app.route('/update-product-quantity', methods=['POST'])
def update_product_quantity():
    data = request.get_json()
    product_id = data.get('productId')
    quantity = data.get('quantity')
    
    product = db.session.query(Product).filter_by(ProductID=product_id).first()
    
    if product:
        if product.Quantity - quantity < 0:
            return jsonify({'error': '庫存不足，無法完成此更新'}), 400  # 如果庫存不足，返回400錯誤
        product.Quantity -= quantity  # 假設庫存數量減少
        db.session.commit()
        return jsonify({'message': '庫存更新成功'}), 200
    else:
        return jsonify({'error': '產品不存在'}), 404



@app.route('/update_order_status', methods=['POST'])
def update_order_status():
    data = request.get_json()
    order_id = data.get('order_id')
    status_type = data.get('status_type')
    new_status = data.get('status')

    if order_id is None or status_type is None or new_status is None:
        return jsonify({'success': False, 'message': '缺少必要參數'}), 400

    if status_type not in ['OrderStatusID', 'PaymentStatusID', 'DeliveryStatusID']:
        return jsonify({'success': False, 'message': '無效的狀態類型'}), 400

    try:
        order = Orders.query.get(order_id)
        if order:
            if status_type == 'OrderStatusID':
                order.OrderStatusID = new_status
            elif status_type == 'PaymentStatusID':
                order.PaymentStatusID = new_status
            elif status_type == 'DeliveryStatusID':
                order.DeliveryStatusID = new_status
            
            db.session.commit()
            return jsonify({'success': True}), 200
        else:
            return jsonify({'success': False, 'message': '訂單不存在'}), 404
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"更新訂單狀態時發生錯誤: {e}")
        return jsonify({'success': False, 'message': '更新失敗'}), 500

@app.route('/api/orders', methods=['GET'])
def api_orders():
    page = int(request.args.get('page', 1))
    status = request.args.get('status', '')
    search = request.args.get('search', '')

    try:
        query = Orders.query

        if status:
            query = query.filter(Orders.OrderStatusID == status)
        
        if search:
            query = query.filter(Orders.CustomerName.like(f'%{search}%'))

        total_orders = query.count()
        orders = query.paginate(page, per_page=10, error_out=False)

        return jsonify({
            'orders': [{
                'order_id': order.OrderID,
                'customer_name': order.CustomerName,
                'total_amount': float(order.TotalPrice),
                'status': order.OrderStatusID
            } for order in orders.items],
            'total_pages': orders.pages,
            'current_page': orders.page
        })
    except Exception as e:
        app.logger.error(f"查詢訂單時發生錯誤: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/products', methods=['GET', 'POST'])
def products():
    if not session.get('logged_in'):
        return redirect(url_for('manager_login'))

    search_target = request.form.get('search_target') if request.method == 'POST' else request.args.get('search_target')
    search_value = request.form.get('search_value', '').strip() if request.method == 'POST' else request.args.get('search_value', '').strip()

    pagination = None
    message = None
    all_products = []

    if search_target:
        if search_target == 'showWeb':
            all_products = Product.query.filter_by(Status=True).order_by(Product.ProductName).all()
        elif search_target == 'availability':
            all_products = Product.query.filter_by(is_available=True).order_by(Product.ProductName).all()
        elif search_target == 'name' and search_value:
            all_products = Product.query.filter(Product.ProductName.ilike(f'%{search_value}%')).order_by(Product.ProductName).all()
        else:
            message = '沒有符合條件的商品'
    else:
        page = request.args.get('page', 1, type=int)
        per_page = 10
        query = Product.query.order_by(
            db.case(
                (Product.is_available == True, 1),
                (Product.Status == True, 2),
                else_=3
            ),
            Product.ProductName
        )
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        all_products = pagination.items

        if not all_products:
            message = '目前沒有商品顯示'

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        html = render_template('product_list.html', products=all_products)
        return jsonify({'html': html})

    return render_template('products.html', products=all_products, pagination=pagination, message=message)

@app.route('/products/search_by_name', methods=['GET'])
def search_by_name():
    name = request.args.get('name')
    if name:
        products = Product.query.filter(Product.ProductName.like(f'%{name}%')).all()
        return jsonify([product.to_dict() for product in products])
    return jsonify({'status': 'error', 'message': '無效的搜尋關鍵字'}), 400

@app.route('/products/show_web', methods=['GET'])
def show_web():
    products = Product.query.filter_by(Status=True).all()
    return jsonify([product.to_dict() for product in products])

@app.route('/products/availability', methods=['GET'])
def availability():
    products = Product.query.filter_by(is_available=True).all()
    return jsonify([product.to_dict() for product in products])

@app.route('/update_product/<int:product_id>', methods=['POST'])
def update_product(product_id):
    # 查詢產品
    product = Product.query.get(product_id)
    if not product:
        flash('產品未找到', 'error')
        return redirect(url_for('product_edit', product_id=product_id))
    
    # 獲取來自表單的資料
    product_name = request.form.get('ProductName')
    notes = request.form.get('Notes')
    price = request.form.get('Price')
    quantity = request.form.get('Quantity')
    ingredients = request.form.get('Ingredients')
    origin = request.form.get('Origin')
    
    # 更新產品資料
    updated = False
    if product_name:
        product.ProductName = product_name
        updated = True
    if notes:
        product.Notes = notes
        updated = True
    if price:
        product.Price = price
        updated = True
    if quantity:
        product.Quantity = quantity
        updated = True
    if ingredients:
        product.Ingredients = ingredients
        updated = True
    if origin:
        product.Origin = origin
        updated = True
    
    if updated:
        try:
            # 保存更改到資料庫
            db.session.commit()
            flash('產品資料已更新', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'更新產品資料時發生錯誤: {str(e)}', 'error')
    else:
        flash('沒有任何變更需要更新', 'info')
    
    return redirect(url_for('product_edit', product_id=product_id))
    
@app.route('/upload_image/<int:product_id>', methods=['POST'])
def upload_image(product_id):
    if 'image' not in request.files:
        flash('沒有選擇圖片', 'error')
        return redirect(url_for('product_edit', product_id=product_id))
    
    image = request.files['image']
    if image.filename == '':
        flash('沒有選擇圖片', 'error')
        return redirect(url_for('product_edit', product_id=product_id))
    
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        flash('GitHub token 未設定', 'error')
        return redirect(url_for('product_edit', product_id=product_id))

    # 上傳圖片到 GitHub
    success = upload_image_to_github(
        repo_owner="selina029",
        repo_name="test",
        file=image,
        commit_message=f"Upload {image.filename} to test/static/uploads",
        github_token=github_token
    )
    
    if success:
        flash('圖片上傳成功', 'success')
    else:
        flash('圖片上傳到 GitHub 失敗', 'error')
    
    return redirect(url_for('product_edit', product_id=product_id))


@app.route('/products/toggle_status/<int:product_id>', methods=['POST'])
def toggle_status(product_id):
    product = db.session.get(Product, product_id)
    if product:
        product.Status = not product.Status
        db.session.commit()

        return jsonify({'status': 'success', 'new_status': '上架' if product.Status else '下架'})
    return jsonify({'status': 'error', 'message': '產品不存在'}), 404

@app.route('/products/toggle_availability/<int:product_id>', methods=['POST'])
def toggle_product_availability(product_id):
    product = db.session.get(Product, product_id)
    if product:
        product.is_available = not product.is_available
        db.session.commit()
        return jsonify({'status': 'success', 'is_available': product.is_available})
    return jsonify({'status': 'error', 'message': '產品不存在'}), 404


@app.route('/product/<int:product_id>', methods=['GET'])
def product_edit(product_id):
    product = Product.query.get_or_404(product_id)
    images = ProductImage.query.filter_by(ProductID=product_id).all()
    return render_template('product_edit.html', product=product, images=images)

def delete_image_from_github(repo_owner, repo_name, file_path, commit_message, github_token):
    api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{file_path}"

    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json"
    }

    # 獲取 sha 值以便刪除
    response = requests.get(api_url, headers=headers)
    if response.status_code == 200:
        sha = response.json()["sha"]
    else:
        print(f"GitHub API error (fetch sha): {response.status_code} - {response.text}")
        return False

    payload = {
        "message": commit_message,
        "sha": sha
    }

    response = requests.delete(api_url, json=payload, headers=headers)

    if response.status_code == 200:
        return True
    else:
        print(f"GitHub API error (delete): {response.status_code} - {response.text}")
        return False

@app.route('/delete_image/<int:image_id>', methods=['POST'])
def delete_image(image_id):
    image = ProductImage.query.get(image_id)
    if image is None:
        flash('圖片未找到', 'error')
        return redirect(url_for('product_edit', product_id=image.ProductID))
    
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        flash('GitHub token 未設定', 'error')
        return redirect(url_for('product_edit', product_id=image.ProductID))

    # 刪除圖片檔案
    success = delete_image_from_github(
        repo_owner="selina029",
        repo_name="test",
        file_path=f"static/uploads/{image.ImagePath}",
        commit_message=f"Delete {image.ImagePath} from test/static/uploads",
        github_token=github_token
    )
    
    if success:
        db.session.delete(image)
        db.session.commit()
        flash('圖片已刪除', 'success')
    else:
        flash('圖片刪除失敗', 'error')
    
    return redirect(url_for('product_edit', product_id=image.ProductID))

@app.route('/notify_homepage', methods=['POST'])
def notify_homepage():
    try:
        # 實現首頁更新邏輯
        return jsonify({'status': 'success', 'message': '首頁已更新'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/manager_logout')
def manager_logout():
    session.pop('logged_in', None)
    session.pop('username', None)
    return redirect(url_for('manager_login'))

@app.route('/')
def index():
    return redirect(url_for('home'))

@app.route('/add_register')
def add_register():
    return render_template('register.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    user_id_hash = request.args.get('user_id')  # 從查詢字符串獲取哈希的 user_id
    original_user_id = get_original_user_id(user_id_hash)  # 從資料庫獲取原始的 user_id

    print(f"Received User ID Hash: {user_id_hash}")
    print(f"Converted Original User ID: {original_user_id}")

    form = RegisterForm()

    if form.validate_on_submit():
        print("Form validated successfully")

        # 獲取表單數據
        name = form.name.data
        phone = form.phone.data
        email = form.email.data
        password = form.password.data
        birthday = form.birthday.data
        user_id = form.user_id.data  # 直接從表單中獲取 user_id

        print(f"Name: {name}, Phone: {phone}, Email: {email}, Birthday: {birthday}, User ID: {user_id}")

        # 檢查是否已存在相同的郵箱或電話
        existing_member = Register.query.filter((Register.Email == email) | (Register.Phone == phone)).first()
        if existing_member:
            flash("此信箱或電話號碼已被註冊", "danger")
        else:
            # 創建新會員並保存到數據庫
            member = Register(name=name, phone=phone, email=email, password=password, birthday=birthday, user_id=user_id)  # 使用表單獲取的 user_id
            db.session.add(member)
            try:
                db.session.commit()
                flash("註冊成功，請登入", "success")
                return redirect(url_for('login'))
            except IntegrityError as e:
                db.session.rollback()
                flash(f"註冊失敗：{str(e)}", "danger")
    else:
        print(form.errors)
        flash("表單驗證失敗，請檢查輸入。", "danger")

    return render_template('register2.html', form=form, user_id=original_user_id)

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    next_page = request.args.get('next') or url_for('home')  # Default redirect to home
    if form.validate_on_submit():
        phone = form.phone.data
        password = form.password.data
        member = Register.query.filter_by(Phone=phone).first()
       
        if member and member.check_password(password):
            # Create User instance and log them in
            user = User(id=member.MemberID, name=member.Name, phone=member.Phone, email=member.Email)
            login_user(user)  # Flask-Login handles login state
            
            # Store member_id in session
            session['member_id'] = member.MemberID
           
            # Retrieve cart from session or localStorage
            cart = session.get('cart', [])  # Use session to temporarily store cart
           
            # Save cart items for logged-in user
            if cart:
                for item in cart:
                    product_id = item['product_id']
                    quantity = item['quantity']
                    cart_item = CartItem.query.filter_by(MemberID=user.id, ProductID=product_id).first()
                    if cart_item:
                        cart_item.quantity += quantity
                    else:
                        cart_item = CartItem(MemberID=user.id, ProductID=product_id, quantity=quantity)
                        db.session.add(cart_item)
                db.session.commit()
                session.pop('cart', None)  # Clear cart from session

            flash("Login successful", "success")
            return redirect(next_page)
        else:
            flash("Invalid login credentials", "danger")
    return render_template('login2.html', form=form)

@app.before_request
def check_login():
    # Remove enforced login logic; check login status only when needed
    pass

@app.route('/logout', methods=['POST'])
@login_required
def logout():
    # Save cart to session
    cart_items = CartItem.query.filter_by(MemberID=current_user.id).all()
    cart = [{'product_id': item.ProductID, 'quantity': item.quantity} for item in cart_items]
    session['cart'] = cart  # Store cart in session
    
    # Clear member_id from session
    session.pop('member_id', None)
    
    logout_user()
    return redirect(url_for('home'))

# LINE 登入路由
@app.route('/line_login', methods=['GET'])
def line_login():
    line_login_url = (
        'https://access.line.me/oauth2/v2.1/authorize?'
        'response_type=code&'
        f'client_id={LINE_CHANNEL_ID}&'
        f'redirect_uri={LINE_REDIRECT_URI}&'
        'state=random_string&'
        'scope=profile%20openid%20email'
    )
    return redirect(line_login_url)

# LINE 回調路由
@app.route('/line_callback')
def line_callback():
    code = request.args.get('code')
    token_url = 'https://api.line.me/oauth2/v2.1/token'
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': LINE_REDIRECT_URI,
        'client_id': LINE_CHANNEL_ID,
        'client_secret': LINE_CHANNEL_SECRET
    }

    token_response = requests.post(token_url, headers=headers, data=data)
    token_json = token_response.json()
    access_token = token_json.get('access_token')

    if not access_token:
        flash("LINE 登入失敗", "danger")
        return redirect(url_for('login'))

    profile_url = 'https://api.line.me/v2/profile'
    profile_headers = {'Authorization': f'Bearer {access_token}'}
    profile_response = requests.get(profile_url, headers=profile_headers)
    profile_json = profile_response.json()

    user_id = profile_json.get('userId')
    display_name = profile_json.get('displayName')
    picture_url = profile_json.get('pictureUrl')

    member = Register.query.filter_by(LineID=user_id).first()
    if not member:
        member = Register(name=display_name, email=None, password=None, phone=None, LineID=user_id)
        db.session.add(member)
        db.session.commit()

    user = User(id=member.MemberID, name=member.Name, phone=member.Phone, email=member.Email)
    login_user(user)
    session['member_id'] = member.MemberID
    flash("LINE 登入成功", "success")
    return redirect(url_for('home'))

@app.route('/cart')
@login_required
def cart():
    try:
        # 獲取使用者的購物車項目
        cart_items = CartItem.query.filter_by(MemberID=current_user.id).all()
        return render_template('shoppingcar.html', cart_items=cart_items)
    except Exception as e:
        print(f'Error retrieving cart items: {e}')
        return jsonify({'error': 'An error occurred while retrieving cart items'}), 500

@app.route('/get_product_by_name/<product_name>', methods=['GET'])
def get_product_by_name(product_name):
    product_name = product_name.replace('%20', ' ')  # 處理 URL 編碼中的空格
    product = Product.query.filter_by(ProductName=product_name).first()
    if product:
        return jsonify({
            'ProductID': product.ProductID,
            'name': product.ProductName,
            'price': str(product.Price)
        })
    return jsonify({'error': 'Product not found'}), 404

@app.route('/update_quantity', methods=['POST'])
@login_required
def update_quantity():
    data = request.get_json()
    product_id = data.get('ProductID')
    quantity = data.get('quantity')

    if not product_id or quantity is None:
        return jsonify({'error': '缺少 ProductID 或 quantity'}), 400

    try:
        quantity = int(quantity)
        if quantity < 1:
            return jsonify({'error': '數量必須大於 0'}), 400
    except ValueError:
        return jsonify({'error': '數量必須是數字'}), 400

    cart_item = CartItem.query.filter_by(ProductID=product_id, MemberID=current_user.id).first()
    if not cart_item:
        return jsonify({'error': '找不到該購物車項目'}), 404

    cart_item.quantity = quantity
    db.session.commit()

    product = Product.query.get(product_id)
    if not product:
        return jsonify({'error': '找不到產品'}), 404

    subtotal = product.Price * quantity

    return jsonify({'subtotal': str(subtotal), 'success': True}), 200

@app.route('/add_to_cart', methods=['POST'])
@login_required
def add_to_cart():
    try:
        data = request.get_json()
        ProductID = data.get('ProductID')
        quantity = data.get('quantity')

        if ProductID is None or quantity is None:
            return jsonify({'success': False, 'message': 'Invalid data'}), 400

        product = Product.query.get(ProductID)
        if product is None:
            return jsonify({'success': False, 'message': 'Product not found'}), 404

        cart_item = CartItem.query.filter_by(ProductID=ProductID, MemberID=current_user.id).first()
        if cart_item:
            cart_item.quantity += quantity
        else:
            cart_item = CartItem(
                MemberID=current_user.id,
                ProductID=ProductID,
                quantity=quantity
            )
            db.session.add(cart_item)

        db.session.commit()

        subtotal = product.Price * quantity

        return jsonify({'success': True, 'message': 'Item added to cart', 'subtotal': subtotal}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/delete_item', methods=['POST'])
@login_required
def delete_item():
    data = request.json
    ProductID = data.get('ProductID')
   
    cart_item = CartItem.query.filter_by(ProductID=ProductID, MemberID=current_user.id).first()
   
    if cart_item:
        db.session.delete(cart_item)
        db.session.commit()
        return jsonify({'success': True}), 200
    else:
        return jsonify({'success': False, 'message': 'Item not found'}), 404

@app.route('/member')
@login_required
def member():
    if current_user.is_authenticated:
        member = Register.query.get(current_user.id)
        if member:
            return render_template('member.html', member=member)
   
    return "會員未找到或未登入", 404

@app.route('/member/update', methods=['POST'])
def update_member():
    if not current_user.is_authenticated:
        return jsonify(success=False, message='您需要登入才能更新資料')

    username = request.form.get('username')
    email = request.form.get('email')
    phone = request.form.get('phone')
    old_password = request.form.get('old_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    
    member = Register.query.filter_by(MemberID=current_user.id).first()
    if not member:
        return jsonify(success=False, message='用戶不存在')

    # 驗證舊密碼是否正確
    if old_password and not member.check_password(old_password):
        return jsonify(success=False, message='舊密碼錯誤')

    # 驗證新密碼與確認密碼是否一致
    if new_password and new_password != confirm_password:
        return jsonify(success=False, message='新密碼與確認密碼不一致')
    
    # 更新使用者資料
    member.Name = username
    member.Email = email
    member.Phone = phone

    # 如果提供了新密碼，則更新密碼
    if new_password:
        member.set_password(new_password)

    db.session.commit()
    return jsonify(success=True, message='資料更新成功')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')


@app.route('/home')
def home():
    page = request.args.get('page', 1, type=int)
    per_page = 9
    pagination = Product.query.filter_by(Status=True).order_by(
        Product.ProductName,
        Product.is_available.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    # 默認 cart_item_count 為 0，若用戶登入則更新為實際數量
    cart_item_count = 0
    if current_user.is_authenticated:
        member_id = current_user.id
        cart_item_count = CartItem.query.filter_by(MemberID=member_id).count()
   
    # 檢查用戶是否已經登入
    is_authenticated = current_user.is_authenticated

    return render_template('home.html', products=pagination.items, pagination=pagination, cart_item_count=cart_item_count, is_authenticated=is_authenticated)


@app.route('/api/cart_status')
@login_required
def cart_status():
    try:
        cart_item_count = CartItem.query.filter_by(MemberID=current_user.id).count()
        return jsonify({'cart_item_count': cart_item_count})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/search', methods=['GET'])
def search():
    query = request.args.get('query', '')
    page_type = request.args.get('page_type', 'home')  # 取得頁面類型
    per_page = 9

    # 查詢條件
    if query:
        products_query = Product.query.filter(Product.ProductName.ilike(f'%{query}%'))
    else:
        products_query = Product.query.filter(Product.Status == True)

    # 如果是首頁搜尋，直接返回產品列表
    if page_type == 'home':
        products = products_query.filter(Product.is_available == True).paginate(page=1, per_page=per_page, error_out=False)
        return render_template('home.html', products=products.items, pagination=products)

    # 否則，處理團購和已結束團購的產品查詢和分頁
    group_page = request.args.get('group_page', 1, type=int)  # 團購頁面的頁碼
    ended_page = request.args.get('ended_page', 1, type=int)  # 已結束頁面的頁碼

    available_products_query = products_query.filter(Product.is_available == True)
    unavailable_products_query = products_query.filter(Product.is_available == False)

    available_pagination = available_products_query.paginate(page=group_page, per_page=per_page, error_out=False)
    unavailable_pagination = unavailable_products_query.paginate(page=ended_page, per_page=per_page, error_out=False)

    return render_template('group.html',
                           available_products=available_pagination.items,
                           unavailable_products=unavailable_pagination.items,
                           available_pagination=available_pagination,
                           unavailable_pagination=unavailable_pagination,
                           group_page=group_page,
                           ended_page=ended_page)


@app.route('/product/<int:product_id>')
def get_product(product_id):
    product = Product.query.get_or_404(product_id)
    images = ProductImage.query.filter_by(ProductID=product_id).order_by(ProductImage.ImageOrder).all()
   
    product_data = {
        'ProductName': product.ProductName,
        'Price': str(product.Price),
        'Quantity': product.Quantity,
        'Ingredients': product.Ingredients,
        'Origin': product.Origin,
        'Notes': product.Notes,
        'Images': [image.ImagePath for image in images]
    }
   
    return jsonify(product_data)

@app.route('/product_detail/<int:product_id>')
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    is_authenticated = current_user.is_authenticated  # Ensure this is defined
    return render_template('productDetail.html', product=product, is_authenticated=is_authenticated)

@app.route('/api/product', methods=['GET'])
def fetch_product():
    product_id = request.args.get('ProductID', type=int)
    if product_id:
        product_data = fetch_product_from_database(product_id)
        if product_data:
            return jsonify(product_data)
        else:
            return jsonify({'error': 'Product not found'}), 404
    else:
        return jsonify({'error': 'ProductID is required'}), 400

def fetch_product_from_database(product_id):
    product = Product.query.filter_by(ProductID=product_id).first()
    if product:
        return {
            'ProductID': product.ProductID,
            'ProductName': product.ProductName,
            'Quantity': product.Quantity,
            'Price': product.Price
        }
    return None

@app.route('/group')
def group():
    available_page = request.args.get('available_page', 1, type=int)
    unavailable_page = request.args.get('unavailable_page', 1, type=int)
    per_page = 12  # 每頁顯示12個產品

    # 對可用產品進行分頁並排序
    available_products_pagination = Product.query.filter_by(is_available=True).order_by(Product.ProductName).paginate(page=available_page, per_page=per_page, error_out=False)
    available_products = available_products_pagination.items

    # 對不可用產品進行分頁並排序
    unavailable_products_pagination = Product.query.filter_by(is_available=False).order_by(Product.ProductName).paginate(page=unavailable_page, per_page=per_page, error_out=False)
    unavailable_products = unavailable_products_pagination.items

    cart_item_count = 0
    if current_user.is_authenticated:
        member_id = current_user.id
        cart_item_count = CartItem.query.filter_by(MemberID=member_id).count()

    return render_template(
        'group.html',
        available_products=available_products,
        unavailable_products=unavailable_products,
        available_pagination=available_products_pagination,
        unavailable_pagination=unavailable_products_pagination,
        cart_item_count=cart_item_count
    )


@app.route('/get_products')
def get_products():
    products = Product.query.all()
    products_data = []
    for product in products:
        images = [{'ImagePath': image.ImagePath} for image in product.images]
        products_data.append({
            'ProductID': product.ProductID,
            'ProductName': product.ProductName,
            'Price': product.Price,
            'images': images
        })
    return jsonify({'products': products_data})

@app.route('/checkout', methods=['POST'])
def checkout():
    if 'member_id' not in session:
        return jsonify({'success': False, 'message': '未登入'})

    member_id = session['member_id']
    print(f"Member ID: {member_id}")

    # 檢查購物車中是否有尚未結帳的項目
    cart_items = CartItem.query.filter_by(MemberID=member_id).all()
    if cart_items:
        return jsonify({'success': False, 'message': '您的購物車中有尚未結帳的項目，請先處理這些項目或清空購物車。'})

    # 獲取購物車項目
    data = request.get_json()
    cart_items = data.get('cartItems', [])

    if not cart_items:
        return jsonify({'success': False, 'message': '購物車為空'})

    try:
        # 檢查每個購物車項目
        for item in cart_items:
            product_id = item['productId']
            quantity = item['quantity']

            # 確保產品存在
            product = Product.query.filter_by(ProductID=product_id).first()
            if not product:
                return jsonify({'success': False, 'message': f'產品 ID {product_id} 不存在'})

            # 檢查庫存數量
            if quantity <= 0:
                return jsonify({'success': False, 'message': '數量必須大於 0'})
            if quantity > product.Quantity:
                return jsonify({'success': False, 'message': f'產品 ID {product_id} 庫存不足'})

            # 如果驗證通過，將購物車項目添加到訂單
            cart_item = CartItem(MemberID=member_id, ProductID=product_id, quantity=quantity)
            db.session.add(cart_item)

        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        print(f"Error: {e}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/checkout/check_cart_items', methods=['GET'])
def check_cart_items():
    if 'member_id' not in session:
        return jsonify({'has_unchecked_items': False})

    member_id = session['member_id']
    cart_items = CartItem.query.filter_by(MemberID=member_id).all()
    return jsonify({'has_unchecked_items': len(cart_items) > 0})

@app.route('/checkout/delete_unchecked_cart_items', methods=['DELETE'])
def delete_unchecked_cart_items():
    if 'member_id' not in session:
        return jsonify({'success': False, 'message': '未登入'})

    member_id = session['member_id']
    try:
        # 刪除購物車中的所有項目
        CartItem.query.filter_by(MemberID=member_id).delete()
        db.session.commit()
        return jsonify({'success': True, 'message': '未結帳的購物車項目已刪除'})
    except Exception as e:
        db.session.rollback()
        print(f"Error: {e}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/pay', methods=['GET'])
@login_required
def pay():
    if 'member_id' not in session:
        return redirect(url_for('login'))  
    member_id = session['member_id']
    cart_items = db.session.query(CartItem, Product).join(Product, CartItem.ProductID == Product.ProductID)\
                  .filter(CartItem.MemberID == member_id).all()
    cart_items_list = [
        {
            'product': {
                'ProductID': item.Product.ProductID,
                'ProductName': item.Product.ProductName,
                'Price': str(item.Product.Price)
            },
            'CartItem': {
                'id': item.CartItem.id,
                'quantity': item.CartItem.quantity
            }
        }
        for item in cart_items
    ]

    subtotal = sum(float(item['product']['Price']) * item['CartItem']['quantity'] for item in cart_items_list)
    shipping_fee = 50
    total = subtotal + shipping_fee
    return render_template('pay.html', cart_items=cart_items_list, subtotal=subtotal, shipping_fee=shipping_fee, total=total)

@app.route('/order')
@login_required
def order():
    try:
        # 獲取當前用戶的會員編號
        user_member_id = current_user.id
       
        # 根據會員編號過濾訂單，並按送出時間排序
        orders = Orders.query.filter_by(MemberID=user_member_id).order_by(Orders.OrderDate.desc()).all()

        # 為每個訂單生成哈希值
        for order in orders:
            order.hash = hash_order_id(order.OrderID)
       
        print(f"Orders for user {user_member_id}: {orders}")  # 打印當前用戶的訂單資料
        return render_template('order.html', orders=orders)
    except Exception as e:
        print(f"Error retrieving orders for user {current_user.id}: {e}")
        return "An error occurred while retrieving orders.", 500
    
@app.route('/order_detail/<string:hashed_order_id>')
@login_required
def order_detail(hashed_order_id):
    try:
        # 從資料庫中查詢所有訂單
        orders = Orders.query.all()

        # 使用反哈希函數檢查哈希值是否匹配
        order = next((order for order in orders if verify_hash_order_id(hashed_order_id, order.OrderID)), None)

        if order is None:
            abort(404)  # 如果找不到訂單，返回 404 錯誤

        # 查詢訂單的詳細資訊
        order_details = db.session.query(OrderDetails).filter_by(OrderID=order.OrderID).all()

        # 確保只取一筆唯一的收貨人資訊
        unique_details = order_details[0] if order_details else None

        return render_template('order-detail.html', order=order, unique_details=unique_details)
    except Exception as e:
        print(f"Error retrieving order detail: {e}")
        return "An error occurred while retrieving the order detail.", 500
 
@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        user = Register.query.filter_by(Email=email).first()
        if user:
            token = secrets.token_urlsafe(16)
            user.reset_token = token
            db.session.commit()
            send_reset_email(user)
            flash('重設密碼的連結已發送到您的電子郵件。', 'info')
            return redirect(url_for('login'))
        else:
            flash('該電子郵件未綁定任何帳號。', 'danger')
    return render_template('forgot_password.html')

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    app.logger.debug(f"重設密碼的 token: {token}")

    user = Register.query.filter_by(reset_token=token).first()
    if not user:
        flash('無效的或已過期的重設連結。', 'danger')
        return redirect(url_for('forgot_password'))

    error_message = None

    if request.method == 'POST':
        new_password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if not new_password or not confirm_password:
            error_message = '請填寫所有必填欄位。'
        elif len(new_password) < 6:
            error_message = '新密碼必須至少6位數。'
        elif new_password != confirm_password:
            error_message = '新密碼與確認密碼不一致。'
        else:
            # 更新使用者密碼
            hashed_password = generate_password_hash(new_password, method='scrypt', salt_length=16)
            user.Password = hashed_password
            user.reset_token = None

            try:
                app.logger.debug(f"嘗試提交資料庫更新: {user.Email}")
                db.session.commit()
                flash('您的密碼已更新。', 'success')
                return redirect(url_for('login'))
            except Exception as e:
                db.session.rollback()
                app.logger.error(f'更新密碼時出錯: {str(e)}')
                flash(f'更新密碼時出錯: {str(e)}', 'danger')

    return render_template('reset_password.html', token=token, error_message=error_message)

@app.route('/submit_order', methods=['POST'])
@login_required
def submit_order():
    member_id = current_user.id

    if not member_id:
        return redirect(url_for('login'))

    # 獲取會員資料
    member = db.session.get(Register, member_id)
    if not member:
        return jsonify({'error': '會員資料未找到'}), 404

    # 獲取會員的基本資料
    customer_name = member.Name
    customer_phone = member.Phone
    customer_email = member.Email

    # 獲取 user_id
    registered_user_id = member.user_id  # 這裡讀取 register 表的 user_id

    data = request.json
    shipping_address = data.get('shippingAddress', '')
    receiver_name = data.get('receiverName', '')
    receiver_phone = data.get('receiverPhone', '')
    remittance_code = data.get('remittanceCode', '')

    if not receiver_name or not receiver_phone:
        return jsonify({'error': '收件人姓名和電話為必填欄位'}), 400

    subtotal = calculate_subtotal(member_id)
    shipping_fee = calculate_shipping_fee()
    total_price = subtotal + shipping_fee

    # 建立訂單
    order = Orders(
        MemberID=member_id,
        CustomerName=customer_name,
        Subtotal=subtotal,
        ShippingFee=shipping_fee,
        TotalPrice=total_price,
        OrderStatusID=ORDER_STATUS_PENDING,
        PaymentStatusID=PAYMENT_STATUS_UNPAID,
        DeliveryStatusID=DELIVERY_STATUS_PREPARING,
        UserID=registered_user_id  # 將 user_id 保存到訂單中
    )

    db.session.add(order)
    db.session.commit()

    # 新增訂單詳細資訊
    cart_items = data.get('cartItems', [])
    order_details = []
    for item in cart_items:
        product = item['product']
       
        # 查詢產品圖片路徑
        product_images = ProductImage.query.filter_by(ProductID=product['ProductID']).all()
        image_path = product_images[0].ImagePath if product_images else None  # 假設取第一張圖片
       
        order_detail = OrderDetails(
            OrderID=order.OrderID,
            ProductID=product['ProductID'],
            ProductName=product['ProductName'],
            ProductImage=image_path,  # 儲存圖片路徑
            UnitPrice=Decimal(product['Price']),
            Quantity=item['CartItem']['quantity'],
            TotalPrice=Decimal(product['Price']) * item['CartItem']['quantity'],
            CustomerName=customer_name,
            CustomerPhone=customer_phone,
            CustomerEmail=customer_email,
            ShippingAddress=shipping_address,
            ReceiverName=receiver_name,
            ReceiverPhone=receiver_phone,
            RemittanceCode=remittance_code
        )

        db.session.add(order_detail)
        order_details.append(order_detail)

    db.session.commit()

    # 刪除購物車資料表中的相關項目
    CartItem.query.filter_by(MemberID=member_id).delete()
    db.session.commit()

    # 發送電子郵件給管理者
    send_order_email(order, order_details)

    return jsonify({'success': True})

@app.route('/get_product_images', methods=['POST'])
def get_product_images():
    data = request.json
    product_ids = data.get('product_ids', [])
    
    # 查詢產品圖片
    images = ProductImage.query.filter(ProductImage.ProductID.in_(product_ids)).all()
    
    # 格式化圖片路徑
    image_paths = {img.ProductID: img.ImagePath for img in images}
    
    # 返回 JSON 響應
    return jsonify(image_paths)
 
@app.route("/callback", methods=['POST'])
def callback():
    if request.method == 'POST':
        signature = request.headers['X-Line-Signature']
        body = request.get_data(as_text=True)

        try:
            events = parser.parse(body, signature)  # 解析傳入的事件
        except InvalidSignatureError:
            return '403 Forbidden', 403
        except LineBotApiError:
            return '400 Bad Request', 400

        for event in events:
            if isinstance(event, MessageEvent):  # 如果是訊息事件
                user_id = event.source.user_id  # 獲取用戶的 user_id
                user_message = event.message.text.strip()

                if user_message == '@關於我們':
                    brand_description = """\
            Tea Lounge 時尚品茶餐飲
               
“環保鐵餐盒 · 無麩質飲食 · 私廚料理 · 餐飲規劃設計”
               
📌☕️Tea Lounge 風格的品茶空間隆重登場，將優雅與自然完美融合。我們精選國際知名品牌 Dilmah 的頂級茶葉，搭配義大利經典 illy 咖啡，為您帶來無與倫比的品飲饗宴。由一支專業的餐飲團隊用心規劃，我們致力於將這些國際頂尖的咖啡茶品與美味餐食推廣到台灣的每一個角落。
               
✨我們的特色在於無麩質與無麩食飲食，選用天然食材，關注健康飲食，並支持台灣小農的產品。每一口茶飲、每一道餐點，都是我們對品質的堅持與承諾。嚴選的茶葉細心佐以 Dilmah 帝瑪茶，為您帶來一場完美無瑕的雙重饗宴。
               
《走進我們的 Tea Lounge，感受茶香馥郁，品味自然健康的生活方式。邀請您一同體驗這個將國際風味與本土特色結合的美妙空間。》
               
https://www.instagram.com/food.is.shiny?igsh=am1iNHNqdm96aXY2
                    """
               
                    line_bot_api.reply_message(
                        event.reply_token,
                        TextSendMessage(text=brand_description)
                    )

                # 當用戶輸入 @會員 時
                elif user_message == '@加入會員':
                    # 檢查用戶是否已經存在於資料庫中
                    existing_user = LineUser.query.filter_by(user_id=user_id).first()

                    if not existing_user:
                        try:
                            new_user = LineUser(user_id=user_id)
                            db.session.add(new_user)
                            db.session.commit()

                            # 生成 user_id 的哈希
                            user_id_hash = hashlib.sha256(user_id.encode()).hexdigest()
                            reply_text = f"您尚未完成註冊，請點擊以下鏈接進行註冊：\n[註冊鏈接](https://tealounge-3pzg.onrender.com/register?user_id={user_id_hash})"
                            line_bot_api.reply_message(
                                event.reply_token,
                                TextSendMessage(text=reply_text)
                            )
                        except Exception as e:
                            db.session.rollback()
                            print(f"新增用戶時發生錯誤: {e}")
                    else:
                        # 用戶已經註冊
                        reply_text = "您已是會員，歡迎使用官網下單！"
                        line_bot_api.reply_message(
                            event.reply_token,
                            TextSendMessage(text=reply_text)
                        )

                elif user_message == '@查詢訂單':
                    line_user = LineUser.query.filter_by(user_id=user_id).first()

                    if line_user:
                        register_user = Register.query.filter_by(user_id=line_user.user_id).first()

                        if register_user:
                            member_id = register_user.MemberID
                            orders = Orders.query.filter_by(MemberID=member_id).all()

                            if orders:
                                if len(orders) == 1:
                                    order = orders[0]
                                    order_status_text = Orders.get_status_text('OrderStatusID', order.OrderStatusID)
                                    payment_status_text = Orders.get_status_text('PaymentStatusID', order.PaymentStatusID)
                                    delivery_status_text = Orders.get_status_text('DeliveryStatusID', order.DeliveryStatusID)

                                    reply_text = (f"訂單號碼: {order.OrderID}\n"
                                                  f"訂單日期: {order.OrderDate.strftime('%Y-%m-%d')}\n"
                                                  f"訂單狀態: {order_status_text}\n"
                                                  f"付款狀態: {payment_status_text}\n"
                                                  f"運送狀態: {delivery_status_text}\n"
                                                  f"總價: {order.TotalPrice}\n"
                                                  f"訂單詳情連結: {url_for('order_detail', hashed_order_id=hash_order_id(order.OrderID), _external=True)}")

                                    line_bot_api.reply_message(
                                        event.reply_token,
                                        TextSendMessage(text=reply_text)
                                    )
                                else:
                                    # 生成按鈕樣板供用戶選擇訂單日期
                                    actions = [
                                        MessageTemplateAction(
                                            label=f"訂單日期: {o.OrderDate.strftime('%Y-%m-%d')}",
                                            text=f"{o.OrderDate.strftime('%Y-%m-%d')}"
                                        ) for o in orders
                                    ]
                                    buttons_template = ButtonsTemplate(
                                        title="查詢訂單",
                                        text="請選擇要查詢的訂單日期，若有多筆相同日期訂單，會依訂單時間順序顯示。",
                                        actions=actions[:4]  # 最多顯示四個按鈕（LINE 限制）
                                    )
                                    template_message = TemplateSendMessage(
                                        alt_text="查詢訂單選擇",
                                        template=buttons_template
                                    )
                                    line_bot_api.reply_message(event.reply_token, template_message)
                            else:
                                reply_text = "找不到您的訂單。"
                                line_bot_api.reply_message(
                                    event.reply_token,
                                    TextSendMessage(text=reply_text)
                                )
                        else:
                            reply_text = "無法找到與您的帳號相關的註冊資料。"
                            line_bot_api.reply_message(
                                event.reply_token,
                                TextSendMessage(text=reply_text)
                            )
                    else:
                        reply_text = "您尚未註冊，請先完成註冊。"
                        line_bot_api.reply_message(
                            event.reply_token,
                            TextSendMessage(text=reply_text)
                        )

                elif re.match(r'\d{4}-\d{2}-\d{2}', user_message):  # 點選日期後直接查詢結果
                    order_date_str = user_message
                    order_date = datetime.strptime(order_date_str, '%Y-%m-%d')
                    start_of_day = datetime.combine(order_date, datetime.min.time())  # 修正時間部分
                    end_of_day = datetime.combine(order_date, datetime.max.time())

                    # 查詢該用戶在指定日期的訂單
                    line_user = LineUser.query.filter_by(user_id=user_id).first()
                    if line_user:
                        register_user = Register.query.filter_by(user_id=line_user.user_id).first()
                        if register_user:
                            member_id = register_user.MemberID
                            orders = Orders.query.filter(
                                Orders.MemberID == member_id,
                                Orders.OrderDate >= start_of_day,
                                Orders.OrderDate <= end_of_day
                            ).all()

                            if orders:
                                reply_text = "\n\n".join(
                                    [f"訂單號碼: {order.OrderID}\n"
                                     f"訂單日期: {order.OrderDate.strftime('%Y-%m-%d')}\n"
                                     f"訂單狀態: {Orders.get_status_text('OrderStatusID', order.OrderStatusID)}\n"
                                     f"付款狀態: {Orders.get_status_text('PaymentStatusID', order.PaymentStatusID)}\n"
                                     f"運送狀態: {Orders.get_status_text('DeliveryStatusID', order.DeliveryStatusID)}\n"
                                     f"總價: {order.TotalPrice}\n"
                                     f"訂單詳情連結: {url_for('order_detail', hashed_order_id=hash_order_id(order.OrderID), _external=True)}"
                                     for order in orders]
                                )
                            else:
                                reply_text = "找不到該日期的訂單。"
                        else:
                            reply_text = "無法找到與您的帳號相關的註冊資料。"
                    else:
                        reply_text = "您尚未註冊，請先完成註冊。"

                    line_bot_api.reply_message(
                        event.reply_token,
                        TextSendMessage(text=reply_text)
                    )

                else:
                    reply_text = "若有任何問題都歡迎與我們聯絡~"
                    line_bot_api.reply_message(
                        event.reply_token,
                        TextSendMessage(text=reply_text)
                    )
        return 'OK'  # 確保最後返回 OK



if __name__ == '__main__':
    app.run()
