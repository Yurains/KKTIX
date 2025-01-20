# =========================================
# KKTIX 自動搶票工具
# =========================================

import sys
import time
import random
import json
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, 
    QHBoxLayout, QLineEdit, QPushButton, QComboBox, QLabel,
    QDialog, QMessageBox, QSpinBox, QInputDialog
)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer
from PyQt5.QtGui import QIcon, QFont
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import ddddocr

# 定義儲存帳號資訊的 JSON 檔案路徑
ACCOUNTS_FILE = 'accounts.json'

class LoginDialog(QDialog):
    """
    登入對話框，用於管理和選擇多個 KKTIX 帳號。
    """
    def __init__(self):
        super().__init__()
        self.initUI()
        self.load_accounts()
        
    def initUI(self):
        """
        初始化登入對話框的使用者介面。
        """
        self.setWindowTitle('KKTIX 登入')
        self.setGeometry(300, 300, 350, 250)
        
        layout = QVBoxLayout()
        
        # 設定字體
        font = QFont("Arial", 10)
        
        # 帳號選擇下拉式選單
        self.account_label = QLabel('選擇帳號:')
        self.account_label.setFont(font)
        self.account_combo = QComboBox()
        self.account_combo.addItem("新增帳號")
        layout.addWidget(self.account_label)
        layout.addWidget(self.account_combo)
        
        # 使用者名稱輸入欄位
        self.username_label = QLabel('使用者名稱或 Email:')
        self.username_label.setFont(font)
        self.username_input = QLineEdit()
        layout.addWidget(self.username_label)
        layout.addWidget(self.username_input)
        
        # 密碼輸入欄位
        self.password_label = QLabel('密碼:')
        self.password_label.setFont(font)
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.password_label)
        layout.addWidget(self.password_input)
        
        # 登入按鈕
        self.login_button = QPushButton('登入')
        self.login_button.setFont(font)
        self.login_button.setIcon(QIcon('icons/login.png'))  # 添加圖標
        self.login_button.clicked.connect(self.handle_login)
        layout.addWidget(self.login_button)
        
        self.setLayout(layout)
        
        # 當選擇不同帳號時更新輸入欄位
        self.account_combo.currentIndexChanged.connect(self.account_selected)
        
    def load_accounts(self):
        """
        載入已儲存的帳號資訊，並新增到下拉式選單中。
        """
        try:
            with open(ACCOUNTS_FILE, 'r') as f:
                self.accounts = json.load(f)
        except FileNotFoundError:
            self.accounts = {}
        
        # 更新下拉選單，將已儲存的帳號名稱加入
        for account in self.accounts.keys():
            self.account_combo.addItem(account)
    
    def account_selected(self, index):
        """
        當選擇帳號時，根據選擇更新使用者名稱和密碼欄位。
        如果選擇「新增帳號」，則清空欄位並允許輸入。
        否則，顯示選擇的帳號的使用者名稱和密碼，並禁用編輯。
        """
        if index == 0:
            # 新增帳號
            self.username_input.clear()
            self.password_input.clear()
            self.username_input.setEnabled(True)
            self.password_input.setEnabled(True)
        else:
            account_name = self.account_combo.currentText()
            credentials = self.accounts.get(account_name, {})
            self.username_input.setText(credentials.get('username', ''))
            self.password_input.setText(credentials.get('password', ''))
            self.username_input.setEnabled(False)
            self.password_input.setEnabled(False)
    
    def handle_login(self):
        """
        處理登入操作，並根據選擇新增或使用已存在的帳號。
        """
        account_name = self.account_combo.currentText()
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        
        # 檢查使用者名稱和密碼是否輸入
        if not username or not password:
            QMessageBox.warning(self, '錯誤', '請輸入使用者名稱和密碼')
            return
        
        if account_name == "新增帳號":
            # 使用 QInputDialog 來獲取新帳號名稱
            account_name, ok = QInputDialog.getText(self, '新增帳號', '請輸入帳號名稱:')
            if ok and account_name:
                if account_name in self.accounts:
                    QMessageBox.warning(self, '錯誤', '帳號名稱已存在')
                    return
                # 儲存新帳號
                self.accounts[account_name] = {'username': username, 'password': password}
                with open(ACCOUNTS_FILE, 'w') as f:
                    json.dump(self.accounts, f, indent=4)
                self.account_combo.addItem(account_name)
                self.account_combo.setCurrentText(account_name)
                QMessageBox.information(self, '成功', '帳號已新增')
            else:
                QMessageBox.warning(self, '錯誤', '帳號名稱無效')
        else:
            # 使用已選擇的帳號，無需儲存
            pass
        
        self.accept()
    
    def get_credentials(self):
        """
        取得使用者輸入的帳號和密碼。
        """
        return self.username_input.text(), self.password_input.text()

class TicketBot(QThread):
    """
    自動搶票機器人，繼承自 QThread 以進行背景處理。
    """
    status_signal = pyqtSignal(str)
    
    def __init__(self, url, ticket_count, keyword, username, password, refresh_interval):
        super().__init__()
        self.url = url
        self.ticket_count = ticket_count
        self.keyword = keyword
        self.username = username
        self.password = password
        self.ocr = ddddocr.DdddOcr()
        self.is_paused = False
        self.is_running = True
        self.refresh_interval = refresh_interval  # 重新整理間隔（秒）
        self.max_refresh_count = 1000  # 最大重新整理次數
        self.random_delay = True  # 是否添加隨機延遲
    
    def pause(self):
        """
        切換暫停狀態。
        """
        self.is_paused = not self.is_paused
        return self.is_paused
    
    def stop(self):
        """
        停止機器人運行。
        """
        self.is_running = False
        self.is_paused = False
        
    def login_kktix(self):
        """
        使用 Selenium 自動登入 KKTIX。
        """
        try:
            # 前往登入頁面
            self.driver.get("https://kktix.com/users/sign_in")
            self.status_signal.emit("正在登入KKTIX...")
            
            # 等待登入表單出現
            username_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "user_login"))
            )
            password_input = self.driver.find_element(By.ID, "user_password")
            login_button = self.driver.find_element(By.CLASS_NAME, "btn-login")
            
            # 輸入帳號密碼
            username_input.send_keys(self.username)
            password_input.send_keys(self.password)
            
            # 點擊登入
            login_button.click()
            
            # 等待登入完成
            time.sleep(3)
            
            # 檢查是否登入成功
            if "sign_in" not in self.driver.current_url:
                self.status_signal.emit("登入成功")
                return True
            else:
                self.status_signal.emit("登入失敗")
                return False
                
        except Exception as e:
            self.status_signal.emit(f"登入過程發生錯誤: {str(e)}")
            return False

    def logout_kktix(self):
        """
        使用 Selenium 自動登出 KKTIX。
        """
        try:
            # 前往登出鏈接，假設有一個登出按鈕或鏈接
            logout_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.LINK_TEXT, "登出"))
            )
            logout_button.click()
            time.sleep(2)
            self.status_signal.emit("已成功登出KKTIX")
            return True
        except Exception as e:
            self.status_signal.emit(f"登出過程發生錯誤: {str(e)}")
            return False
    
    def check_tickets_available(self):
        """
        檢查是否有票可以購買。
        若頁面顯示「已售完」或「準備中」，代表目前無法購票。
        若找不到對應的按鈕，也代表目前不可購票。
        """
        try:
            # 檢查是否有"已售完"的訊息
            sold_out_elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), '已售完')]")
            if sold_out_elements:
                return False
                
            # 檢查是否有"準備中"的訊息
            preparing_elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), '準備中')]")
            if preparing_elements:
                return False
                
            # 尋找下一步按鈕
            next_buttons = self.driver.find_elements(By.CLASS_NAME, "btn-point")
            if not next_buttons:
                return False
                
            return True
        except Exception:
            return False
            
    def refresh_page(self):
        """
        重新整理頁面並等待載入完成。
        """
        try:
            if self.random_delay:
                delay = random.uniform(0.5, 2.0)
                time.sleep(delay)
            self.driver.refresh()
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            return True
        except Exception as e:
            self.status_signal.emit(f"重新整理頁面時發生錯誤: {str(e)}")
            return False
    
    def run(self):
        """
        執行搶票機器人的主要流程。
        """
        try:
            # 初始化瀏覽器
            options = webdriver.ChromeOptions()
            #options.add_argument('--headless')  # 隱藏瀏覽器視窗
            self.driver = webdriver.Chrome(options=options)
            
            # 先進行登入
            if not self.login_kktix():
                self.driver.quit()
                return
            
            # 前往目標網頁
            self.driver.get(self.url)
            refresh_count = 0
            
            while self.is_running:
                if self.is_paused:
                    self.status_signal.emit("程式已暫停")
                    time.sleep(1)
                    continue
                
                # 檢查是否達到最大重新整理次數
                if refresh_count >= self.max_refresh_count:
                    self.status_signal.emit("已達到最大重新整理次數，程式停止")
                    break
                
                # 檢查是否有票
                if not self.check_tickets_available():
                    refresh_count += 1
                    self.status_signal.emit(f"目前沒有票，已重新整理 {refresh_count} 次...")
                    time.sleep(self.refresh_interval)
                    self.refresh_page()
                    continue
                
                self.status_signal.emit("發現可購買的票！")
                
                # 如果有關鍵字要求，檢查頁面內容
                if self.keyword:
                    page_text = self.driver.page_source
                    if self.keyword not in page_text:
                        self.status_signal.emit(f"未找到關鍵字: {self.keyword}")
                        time.sleep(self.refresh_interval)
                        self.refresh_page()
                        continue
                
                # 尋找並點擊下一步按鈕（點選進入票種選擇或購買頁面）
                try:
                    next_button = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.CLASS_NAME, "btn-point"))
                    )
                    next_button.click()
                    self.status_signal.emit("已點擊下一步")
                    
                    # 等待票數輸入框
                    ticket_input = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CLASS_NAME, "ng-pristine"))
                    )
                    
                    # 設定票數
                    self.driver.execute_script(
                        f"arguments[0].value = '{self.ticket_count}'", 
                        ticket_input
                    )
                    self.status_signal.emit(f"已設定票數: {self.ticket_count}")
                    
                    # 觸發 Angular 更新
                    self.driver.execute_script(
                        """
                        var element = arguments[0];
                        var evt = new Event('input', { bubbles: true });
                        element.dispatchEvent(evt);
                        """,
                        ticket_input
                    )

                    # 勾選同意條款 (ID = person_agree_terms)
                    try:
                        agree_checkbox = WebDriverWait(self.driver, 10).until(
                            EC.element_to_be_clickable((By.ID, "person_agree_terms"))
                        )
                        agree_checkbox.click()
                        self.status_signal.emit("已勾選同意條款")
                    except Exception as e:
                        self.status_signal.emit(f"勾選同意條款時發生錯誤: {str(e)}")

                    # 點擊下一步按鈕 (class = btn btn-primary btn-lg)
                    try:
                        final_next_button = WebDriverWait(self.driver, 10).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, ".btn.btn-primary.btn-lg"))
                        )
                        final_next_button.click()
                        self.status_signal.emit("已點擊最終下一步")
                    except Exception as e:
                        self.status_signal.emit(f"點擊最終下一步時發生錯誤: {str(e)}")

                    # 按下確認表單資料按鈕 (class = btn btn-primary btn-lg ng-binding ng-isolate-scope)
                    try:
                        confirm_button = WebDriverWait(self.driver, 10).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, ".btn.btn-primary.btn-lg.ng-binding.ng-isolate-scope"))
                        )
                        confirm_button.click()
                        self.status_signal.emit("已按下確認表單資料按鈕")
                    except Exception as e:
                        self.status_signal.emit(f"點擊確認表單資料按鈕時發生錯誤: {str(e)}")
                    
                    # 等待幾秒鐘以確保操作完成
                    time.sleep(5)
                    
                except Exception as e:
                    self.status_signal.emit(f"設定票數時發生錯誤: {str(e)}")
                    time.sleep(self.refresh_interval)
                    self.refresh_page()
                    continue
                
        except Exception as e:
            self.status_signal.emit(f"錯誤: {str(e)}")
        finally:
            if hasattr(self, 'driver'):
                self.driver.quit()

class MainWindow(QMainWindow):
    """
    主視窗類別，負責顯示和管理使用者介面。
    """
    def __init__(self):
        super().__init__()
        self.initUI()
        self.bot = None
        self.username = ""
        self.password = ""
        self.load_accounts_into_main_combo()
        
        # 初始化 QTimer 來更新時間
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_time)
        self.timer.start(1000)  # 每1000毫秒（1秒）觸發一次
        
    def initUI(self):
        """
        初始化主視窗的使用者介面。
        """
        self.setWindowTitle('KKTIX 自動搶票工具')
        self.setGeometry(100, 100, 800, 600)  # 擴大視窗大小
        
        # 設定主介面樣式
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f0f0f0;
            }
            QLabel {
                font-size: 14px;
            }
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 10px;
                border: none;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QLineEdit, QComboBox, QSpinBox {
                padding: 5px;
                border: 1px solid #ccc;
                border-radius: 3px;
            }
        """)
        
        # 主要布局
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout()
        
        # 版本資訊
        version_label = QLabel('KKTIX 自動搶票工具 v1.0')
        version_label.setFont(QFont("Arial", 16, QFont.Bold))
        version_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(version_label)
        
        # 帳號選擇下拉式選單
        account_layout = QHBoxLayout()
        account_label = QLabel('選擇帳號:')
        account_label.setFont(QFont("Arial", 12))
        self.main_account_combo = QComboBox()
        self.main_account_combo.setPlaceholderText("請先登入")
        self.main_account_combo.setEnabled(False)
        account_layout.addWidget(account_label)
        account_layout.addWidget(self.main_account_combo)
        layout.addLayout(account_layout)
        
        # 登入狀態
        self.login_status = QLabel('尚未登入')
        self.login_status.setFont(QFont("Arial", 12))
        self.login_status.setStyleSheet("color: red;")
        self.login_status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.login_status)
        
        # 登入按鈕
        self.login_button = QPushButton('登入KKTIX')
        self.login_button.setFont(QFont("Arial", 12))
        self.login_button.setIcon(QIcon('icons/login.png'))  # 添加圖標
        self.login_button.clicked.connect(self.show_login_dialog)
        layout.addWidget(self.login_button)
        
        # 登出按鈕
        self.logout_button = QPushButton('登出KKTIX')
        self.logout_button.setFont(QFont("Arial", 12))
        self.logout_button.setIcon(QIcon('icons/logout.png'))  # 添加圖標
        self.logout_button.clicked.connect(self.logout_kktix)
        self.logout_button.setEnabled(False)  # 預設禁用，登入後啟用
        layout.addWidget(self.logout_button)
        
        # URL輸入區域
        url_layout = QHBoxLayout()
        url_label = QLabel('KKTIX URL:')
        url_label.setFont(QFont("Arial", 12))
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("輸入搶票的KKTIX活動網址")
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.url_input)
        layout.addLayout(url_layout)
        
        # 關鍵字輸入區域
        keyword_layout = QHBoxLayout()
        keyword_label = QLabel('關鍵字 (選填):')
        keyword_label.setFont(QFont("Arial", 12))
        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText("輸入特定關鍵字以篩選票種")
        keyword_layout.addWidget(keyword_label)
        keyword_layout.addWidget(self.keyword_input)
        layout.addLayout(keyword_layout)
        
        # 票數選擇
        ticket_layout = QHBoxLayout()
        ticket_label = QLabel('票數:')
        ticket_label.setFont(QFont("Arial", 12))
        self.ticket_combo = QComboBox()
        self.ticket_combo.addItems([str(i) for i in range(1, 11)])  # 增加票數選項
        ticket_layout.addWidget(ticket_label)
        ticket_layout.addWidget(self.ticket_combo)
        layout.addLayout(ticket_layout)
        
        # 刷新間隔調整
        refresh_layout = QHBoxLayout()
        refresh_label = QLabel('刷新間隔 (秒):')
        refresh_label.setFont(QFont("Arial", 12))
        self.refresh_spin = QSpinBox()
        self.refresh_spin.setRange(1, 60)  # 設定刷新間隔範圍為 1 到 60 秒
        self.refresh_spin.setValue(1)      # 預設為 1 秒
        refresh_layout.addWidget(refresh_label)
        refresh_layout.addWidget(self.refresh_spin)
        layout.addLayout(refresh_layout)
        
        # 按鈕布局
        button_layout = QHBoxLayout()
        
        # 開始按鈕
        self.start_button = QPushButton('開始搶票')
        self.start_button.setFont(QFont("Arial", 12))
        self.start_button.setIcon(QIcon('icons/start.png'))  # 添加圖標
        self.start_button.clicked.connect(self.start_bot)
        self.start_button.setEnabled(False)  # 預設禁用，需要先登入
        button_layout.addWidget(self.start_button)
        
        # 暫停按鈕
        self.pause_button = QPushButton('暫停')
        self.pause_button.setFont(QFont("Arial", 12))
        self.pause_button.setIcon(QIcon('icons/pause.png'))  # 添加圖標
        self.pause_button.clicked.connect(self.pause_bot)
        self.pause_button.setEnabled(False)
        button_layout.addWidget(self.pause_button)
        
        # 停止按鈕
        self.stop_button = QPushButton('停止')
        self.stop_button.setFont(QFont("Arial", 12))
        self.stop_button.setIcon(QIcon('icons/stop.png'))  # 添加圖標
        self.stop_button.clicked.connect(self.stop_bot)
        self.stop_button.setEnabled(False)
        button_layout.addWidget(self.stop_button)
        
        layout.addLayout(button_layout)
        
        # 狀態顯示
        self.status_label = QLabel('')
        self.status_label.setFont(QFont("Arial", 12))
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        # 目前時間顯示
        self.time_label = QLabel(f'更新時間: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        self.time_label.setFont(QFont("Arial", 10))
        self.time_label.setAlignment(Qt.AlignRight)
        layout.addWidget(self.time_label)
        
        # 作者資訊和聯絡超連結
        author_label = QLabel('<p style="text-align:right;">'
                              'By Junyan, 2025/1/20<br>'
                              '聯絡作者: <a href="https://www.instagram.com/junyan_0826/">點這裡</a>'
                              '</p>')
        author_label.setOpenExternalLinks(True)  # 允許點擊超連結
        layout.addWidget(author_label)
        
        main_widget.setLayout(layout)
        
    def load_accounts_into_main_combo(self):
        """
        載入已儲存的帳號到主視窗的帳號選擇下拉式選單中。
        """
        try:
            with open(ACCOUNTS_FILE, 'r') as f:
                self.accounts = json.load(f)
        except FileNotFoundError:
            self.accounts = {}
        
        # 更新下拉選單，將已儲存的帳號名稱加入
        for account in self.accounts.keys():
            self.main_account_combo.addItem(account)
        
    def show_login_dialog(self):
        """
        顯示登入對話框，讓使用者選擇或新增帳號並登入。
        """
        dialog = LoginDialog()
        if dialog.exec_() == QDialog.Accepted:
            self.username, self.password = dialog.get_credentials()
            if self.username and self.password:
                self.login_status.setText('已登入')
                self.login_status.setStyleSheet("color: green;")
                self.start_button.setEnabled(True)
                self.login_button.setEnabled(False)
                self.logout_button.setEnabled(True)
                
                # 更新主視窗中的帳號選擇下拉式選單
                self.main_account_combo.clear()
                self.main_account_combo.addItem(self.username)
                self.main_account_combo.setEnabled(True)
            else:
                QMessageBox.warning(self, '錯誤', '請輸入帳號和密碼')
    
    def logout_kktix(self):
        """
        處理登出操作，清除帳號資訊並更新 UI 狀態。
        """
        reply = QMessageBox.question(
            self, '確認登出', '您確定要登出嗎？',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # 清除帳號資訊
            try:
                with open(ACCOUNTS_FILE, 'r') as f:
                    accounts = json.load(f)
            except FileNotFoundError:
                accounts = {}
            
            # 根據目前選擇的帳號名稱移除帳號
            account_name = self.username  # 假設 username 是帳號名稱
            if account_name in accounts:
                del accounts[account_name]
                with open(ACCOUNTS_FILE, 'w') as f:
                    json.dump(accounts, f, indent=4)
                QMessageBox.information(self, '登出成功', f'帳號 {account_name} 已成功登出')
            else:
                QMessageBox.warning(self, '錯誤', '找不到選擇的帳號')
            
            # 更新主視窗中的帳號選擇下拉式選單
            self.main_account_combo.clear()
            for account in accounts.keys():
                self.main_account_combo.addItem(account)
            
            # 更新 UI 狀態
            self.login_status.setText('尚未登入')
            self.login_status.setStyleSheet("color: red;")
            self.start_button.setEnabled(False)
            self.login_button.setEnabled(True)
            self.logout_button.setEnabled(False)
            self.username = ""
            self.password = ""
            
            # 停止並關閉搶票機器人（如果正在運行）
            if self.bot and self.bot.isRunning():
                self.bot.stop()
                self.bot.quit()
                self.bot = None
                self.status_label.setText('搶票機器人已停止')
                self.stop_button.setEnabled(False)
                self.pause_button.setEnabled(False)
            else:
                self.status_label.setText('')
    
    def start_bot(self):
        """
        開始搶票機器人，根據使用者輸入的參數啟動背景線程。
        """
        if not self.username or not self.password:
            QMessageBox.warning(self, '錯誤', '請先登入KKTIX')
            return
            
        url = self.url_input.text()
        if not url:
            QMessageBox.warning(self, '錯誤', '請輸入KKTIX URL')
            return
            
        ticket_count = self.ticket_combo.currentText()
        keyword = self.keyword_input.text()
        refresh_interval = self.refresh_spin.value()
        
        self.bot = TicketBot(url, ticket_count, keyword, self.username, self.password, refresh_interval)
        self.bot.status_signal.connect(self.update_status)
        self.bot.start()
        self.start_button.setEnabled(False)
        self.pause_button.setEnabled(True)
        self.stop_button.setEnabled(True)
        self.status_label.setText('搶票機器人運行中...')
        
    def pause_bot(self):
        """
        暫停或繼續搶票機器人的運行。
        """
        if self.bot and self.bot.isRunning():
            is_paused = self.bot.pause()
            if is_paused:
                self.pause_button.setText('繼續')
                self.status_label.setText("搶票機器人已暫停")
            else:
                self.pause_button.setText('暫停')
                self.status_label.setText("搶票機器人繼續運行")
            
    def stop_bot(self):
        """
        停止搶票機器人的運行。
        """
        if self.bot and self.bot.isRunning():
            self.bot.stop()
            self.bot.quit()
            self.bot = None
            self.status_label.setText('搶票機器人已停止')
            self.start_button.setEnabled(True)
            self.pause_button.setEnabled(False)
            self.pause_button.setText('暫停')
            self.stop_button.setEnabled(False)
    
    def update_status(self, message):
        """
        更新狀態顯示和目前時間。
        """
        self.status_label.setText(message)
        if "錯誤" in message or "完成" in message or "停止" in message:
            self.start_button.setEnabled(True)
            self.pause_button.setEnabled(False)
    
    def update_time(self):
        """
        更新目前時間標籤。
        """
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.time_label.setText(f'更新時間: {current_time}')

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())