import streamlit as st
import json
import firebase_admin
from firebase_admin import credentials, firestore
import re
from streamlit_cookies_manager import EncryptedCookieManager

# Konfigurasi Halaman
st.set_page_config(
    page_title="Sistem Informasi Mahasiswa FMIPA", 
    page_icon="https://www.unud.ac.id/upload/images/logo%20unud%20%282%29%281%29.png",
    layout="wide"
)

# Implementasi Struktur Data
class HashTable:
    def __init__(self, size=1000):
        self.size = size
        self.table = [[] for _ in range(size)]
    
    def _hash(self, key):
        return hash(key) % self.size
    
    def insert(self, key, value):
        hash_key = self._hash(key)
        bucket = self.table[hash_key]
        for i, (k, v) in enumerate(bucket):
            if k == key:
                bucket[i] = (key, value)
                return
        bucket.append((key, value))
    
    def find(self, key):
        hash_key = self._hash(key)
        bucket = self.table[hash_key]
        for k, v in bucket:
            if k == key:
                return v
        return None

class Mahasiswa:
    def __init__(self, nim, nama, email, password):
        self.nim = nim
        self.nama = nama
        self.email = email
        self.password = password

class Angkatan:
    def __init__(self, tahun):
        self.tahun = tahun
        self.mahasiswa_list = []
    
    def tambah_mahasiswa(self, mahasiswa_obj):
        self.mahasiswa_list.append(mahasiswa_obj)

class Prodi:
    def __init__(self, nama, kode_fakultas, kode_prodi):
        self.nama = nama
        self.kode_fakultas = kode_fakultas
        self.kode_prodi = kode_prodi
        self.angkatan_dict = {}
    
    def tambah_angkatan(self, angkatan_obj):
        self.angkatan_dict[angkatan_obj.tahun] = angkatan_obj
    
    def get_angkatan(self, tahun):
        return self.angkatan_dict.get(tahun)

# Inisialisaisi Firebase
def init_firestore():
    try:
        firebase_admin.get_app()
    except ValueError:
        try:
            service_account_file = "sim-mahasiswa-if-firebase-adminsdk.json"
            creds = credentials.Certificate(service_account_file)
            firebase_admin.initialize_app(creds)
        
        except Exception as e:
            st.error("GAGAL MENGINISIALISASI FIREBASE DARI FILE JSON!")
            st.error(f"Pesan Error: {e}")
            st.error(f"Pastikan nama file '{service_account_file}' sudah benar dan berada di dalam folder .streamlit")
            st.stop()
            
    return firestore.client()

# Mengambil data dari database ke struktur data program
def load_data_into_structures(db):
    st.session_state.db_mahasiswa = HashTable()
    st.session_state.tree_root = {}
    
    KODE_PRODI = {
        "Kimia": ("08", "511"),
        "Fisika": ("08", "521"),
        "Biologi": ("08", "531"),
        "Matematika": ("08", "541"),
        "Farmasi": ("08", "551"),
        "Informatika": ("08", "561")
    }
    
    all_prodi_docs = db.collection("FMIPA").stream()
    for prodi_doc in all_prodi_docs:
        prodi_nama = prodi_doc.id
        kode_fakultas, kode_prodi = KODE_PRODI.get(prodi_nama, ("00", "000"))
        prodi_obj = Prodi(prodi_nama, kode_fakultas, kode_prodi)
        st.session_state.tree_root[prodi_nama] = prodi_obj
        
        angkatan_collections = prodi_doc.reference.collections()
        for angkatan_coll in angkatan_collections:
            tahun = int(angkatan_coll.id)
            angkatan_obj = Angkatan(tahun)
            prodi_obj.tambah_angkatan(angkatan_obj)
            
            mahasiswa_docs = angkatan_coll.stream()
            for mhs_doc in mahasiswa_docs:
                nim = mhs_doc.id
                data = mhs_doc.to_dict()
                mhs_obj = Mahasiswa(
                    nim=nim, nama=data.get("nama"), email=data.get("email"),
                    password=data.get("password")
                )
                angkatan_obj.tambah_mahasiswa(mhs_obj)
                st.session_state.db_mahasiswa.insert(nim, mhs_obj)

    st.session_state.admin_password = None
    try:
        admin_doc = db.collection("admin").document("admin").get()
        if admin_doc.exists:
            st.session_state.admin_password = admin_doc.to_dict().get("password")
            st.session_state.admin_email = admin_doc.to_dict().get("email")
    except Exception:
        pass

    st.session_state.cookie_config = {}
    try:
        cookie_doc = db.collection("cookies").document("default_cookie").get()
        if cookie_doc.exists:
            st.session_state.cookie_config = cookie_doc.to_dict()
    except Exception:
        pass

    st.session_state.data_loaded = True

# Fungsi untuk membuat NIM otomatis
def generate_nim(prodi_obj, tahun_angkatan):
    angkatan_obj = prodi_obj.get_angkatan(tahun_angkatan)
    no_urut_terakhir = 0
    if angkatan_obj:
        for mhs in angkatan_obj.mahasiswa_list:
            urut_sekarang = int(mhs.nim[7:])
            if urut_sekarang > no_urut_terakhir:
                no_urut_terakhir = urut_sekarang
    no_urut_baru = no_urut_terakhir + 1
    aa = str(tahun_angkatan)[-2:]
    ff = prodi_obj.kode_fakultas
    ppp = prodi_obj.kode_prodi
    nnn = f"{no_urut_baru:03d}"
    return f"{aa}{ff}{ppp}{nnn}"

# Fungsi untuk membuat email otomatis
def generate_email(nama, nim):
    cleaned_nama = re.sub(r'[^a-zA-Z\s]', '', nama).lower()
    words = cleaned_nama.split()
    last_words = words[-3:]
    email_prefix = "".join(last_words)
    tiga_digit_nim = nim[-3:]
    return f"{email_prefix}{tiga_digit_nim}@student.unud.ac.id"

# Fungsi registrasi mahasiswa baru
def register_new_student(db, nama, nama_prodi, tahun_angkatan, password):
    prodi_obj = st.session_state.tree_root.get(nama_prodi)
    if not prodi_obj:
        return None, "Prodi tidak ditemukan."
    
    new_nim = generate_nim(prodi_obj, tahun_angkatan)
    new_email = generate_email(nama, new_nim)
    
    mhs_baru = Mahasiswa(new_nim, nama, new_email, password)
    
    st.session_state.db_mahasiswa.insert(new_nim, mhs_baru)
    angkatan_obj = prodi_obj.get_angkatan(tahun_angkatan)
    if not angkatan_obj:
        angkatan_obj = Angkatan(tahun_angkatan)
        prodi_obj.tambah_angkatan(angkatan_obj)
    angkatan_obj.tambah_mahasiswa(mhs_baru)
    
    doc_ref = db.collection('FMIPA').document(nama_prodi).collection(str(tahun_angkatan)).document(new_nim)
    doc_ref.set({'nama': nama, 'email': new_email, 'password': password})
    
    return mhs_baru, f"Registrasi berhasil! NIM Anda adalah **{new_nim}**. Silakan login."

# Fungsi login
def check_login(username, password):
    if username.lower() == "admin":
        admin_pw = st.session_state.get("admin_password")
        if admin_pw and password == admin_pw:
            admin_email = st.session_state.get("admin_email", "admin@unud.ac.id")
            return {"email": admin_email}, "admin"
        else:
            return None, None
    else:
        mahasiswa_obj = st.session_state.db_mahasiswa.find(username)
        if mahasiswa_obj and mahasiswa_obj.password == password:
            return mahasiswa_obj, "student"
    return None, None

# Halaman login
def login_page():
    st.title("Login Sistem Informasi Mahasiswa")
    cookies = st.session_state.cookies

    with st.form("login_form"):
        username = st.text_input("Username atau NIM")
        password = st.text_input("Password", type="password")
        remember_me = st.checkbox("Ingat saya") 
        submitted = st.form_submit_button("Login")
        
        if submitted:
            user, role = check_login(username, password)
            if user:
                st.session_state.logged_in = True
                st.session_state.user_info = user
                st.session_state.role = role
                st.session_state.page = "main_app" if role == "student" else "admin_page"
                
                if remember_me:
                    cookie_name = st.session_state.cookie_config.get("name", "sim_auth_session")
                    cookies[cookie_name] = username
                    cookies.save()
                
                st.rerun()
            else:
                st.error("Username atau Password salah!")
    
    if st.button("Register"):
        st.session_state.page = "register"
        st.rerun()

# Halaman register
def register_page():
    st.title("Registrasi Mahasiswa Baru")
    with st.form("register_form"):
        nama = st.text_input("Nama Lengkap")
        nama_prodi = st.selectbox("Program Studi", list(st.session_state.tree_root.keys()))
        tahun_angkatan = st.selectbox("Tahun Angkatan", [2021, 2022, 2023, 2024, 2025])
        password = st.text_input("Buat Password", type="password")
        submitted = st.form_submit_button("Register")
        if submitted:
            db = init_firestore()
            user, message = register_new_student(db, nama, nama_prodi, tahun_angkatan, password)
            if user: st.success(message)
            else: st.error(message)
    
    if st.button("Login"):
        st.session_state.page = "login"
        st.rerun()

# Halaman utama
def main_app():
    user = st.session_state.user_info
    cookies = st.session_state.cookies
    col1, col2 = st.columns([3, 1])
    with col1:
        st.title("Data Diri Mahasiswa")
        st.caption(f"Selamat datang, **{user.nama}**!")
    with col2:
        if st.button("Logout", use_container_width=True):
            cookie_name = st.session_state.cookie_config.get("name", "sim_auth_session")
            if cookie_name in cookies:
                del cookies[cookie_name]
                cookies.save()

            st.session_state.logged_in = False
            st.session_state.page = "login"
            del st.session_state.user_info
            del st.session_state.role
            st.rerun()
    st.markdown("---")
    data_diri = {"Properti": ["NIM", "Nama Lengkap", "Email"], "Value": [user.nim, user.nama, user.email]}
    st.table(data_diri)

# Halaman dashboard admin
def admin_page():
    user = st.session_state.user_info
    cookies = st.session_state.cookies
    col1, col2 = st.columns([3, 1])
    with col1:
        st.title("Dashboard Admin")
        st.caption(f"Login sebagai: **Admin** ({user['email']})")
    with col2:
        if st.button("Logout", use_container_width=True):
            cookie_name = st.session_state.cookie_config.get("name", "sim_auth_session")
            if cookie_name in cookies:
                del cookies[cookie_name]
                cookies.save()
            
            st.session_state.logged_in = False
            st.session_state.page = "login"
            del st.session_state.user_info
            del st.session_state.role
            st.rerun()
    st.markdown("---")
    st.info("Anda memiliki akses penuh untuk melihat seluruh data mahasiswa.")
    root = st.session_state.tree_root
    for prodi_nama, prodi_obj in root.items():
        with st.expander(f"Program Studi: {prodi_nama}"):
            for tahun, angkatan_obj in sorted(prodi_obj.angkatan_dict.items()):
                st.markdown(f"##### Angkatan {tahun}")
                data_for_df = []
                for mhs in angkatan_obj.mahasiswa_list:
                    data_for_df.append({"NIM": mhs.nim, "Nama": mhs.nama, "Email": mhs.email})
                if data_for_df: st.dataframe(data_for_df, use_container_width=True)
                else: st.write("Tidak ada data.")

# Fungsi utama program dan router
def main():
    if "logged_in" not in st.session_state: st.session_state.logged_in = False
    if "data_loaded" not in st.session_state: st.session_state.data_loaded = False
    if 'page' not in st.session_state: st.session_state.page = "login"
    if 'role' not in st.session_state: st.session_state.role = None
    
    if not st.session_state.data_loaded:
        with st.spinner("Menghubungkan ke server dan memuat data..."):
            db = init_firestore()
            load_data_into_structures(db)
        st.rerun()

    cookie_key = st.session_state.cookie_config.get("key", "default_encryption_key")
    st.session_state.cookies = EncryptedCookieManager(password=cookie_key)
    if not st.session_state.cookies.ready():
        st.stop()

    if not st.session_state.logged_in:
        cookie_name = st.session_state.cookie_config.get("name", "sim_auth_session")
        if cookie_name in st.session_state.cookies:
            username_from_cookie = st.session_state.cookies[cookie_name]
            
            user_obj = st.session_state.db_mahasiswa.find(username_from_cookie)
            role = "student" if user_obj else "admin" if username_from_cookie.lower() == 'admin' else None
            
            if user_obj:
                st.session_state.logged_in = True
                st.session_state.user_info = user_obj
                st.session_state.role = role
                st.session_state.page = "main_app"
                st.rerun()
            elif role == "admin":
                 st.session_state.logged_in = True
                 st.session_state.user_info = {"email": st.session_state.get("admin_email", "admin@unud.ac.id")}
                 st.session_state.role = role
                 st.session_state.page = "admin_page"
                 st.rerun()

    if st.session_state.logged_in:
        if st.session_state.role == "student":
            main_app()
        elif st.session_state.role == "admin":
            admin_page()
    else:
        if st.session_state.page == "login":
            login_page()
        elif st.session_state.page == "register":
            register_page()

if __name__ == '__main__':
    main()
