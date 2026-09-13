# -*- coding: utf-8 -*-

import ttkbootstrap as ttk
from ttkbootstrap.scrolled import ScrolledText
from ttkbootstrap.constants import *
from tkinter import filedialog, messagebox
import pandas as pd
import os
import threading
import pyexiv2
import sys
import queue
import re

class MetadataApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ছবি মেটা রাইটার (v11.0 - Auto Rename & PNG Support)")
        self.root.geometry("750x700")
        self.root.resizable(False, False)

        try:
            # নতুন আইকনের নাম my_icon.ico করে দেওয়া হয়েছে
            icon_path = self.resource_path("my_icon.ico")
            self.root.iconbitmap(icon_path)
        except Exception as e:
            print(f"আইকন লোড করা যায়নি: {e}")

        self.csv_path = ttk.StringVar()
        self.image_folder_path = ttk.StringVar()
        self.rename_var = ttk.BooleanVar(value=True) # ডিফল্টভাবে রিনেম অন থাকবে
        self.update_queue = queue.Queue()
        self.processing_active = False
        self.create_widgets()

    def resource_path(self, relative_path):
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding=20)
        main_frame.pack(fill=BOTH, expand=True)
        
        header_label = ttk.Label(main_frame, text="ছবি মেটা রাইটার (Pro)", font=("Segoe UI", 20, "bold"), bootstyle=PRIMARY)
        header_label.pack(pady=(0, 20))
        
        selection_frame = ttk.Labelframe(main_frame, text=" ১. ফাইল এবং ফোল্ডার সিলেক্ট করুন ", bootstyle=INFO, padding=15)
        selection_frame.pack(fill=X, pady=(0, 20))
        
        ttk.Label(selection_frame, text="CSV ফাইল:", font=("Segoe UI", 10)).grid(row=0, column=0, sticky=W, padx=5, pady=(0, 10))
        ttk.Entry(selection_frame, textvariable=self.csv_path, state=READONLY, width=60).grid(row=1, column=0, sticky=EW, padx=5)
        ttk.Button(selection_frame, text="ফাইল বাছুন", command=self.select_csv, bootstyle=OUTLINE).grid(row=1, column=1, padx=(10, 5))
        
        ttk.Label(selection_frame, text="ছবির ফোল্ডার:", font=("Segoe UI", 10)).grid(row=2, column=0, sticky=W, padx=5, pady=(15, 10))
        ttk.Entry(selection_frame, textvariable=self.image_folder_path, state=READONLY, width=60).grid(row=3, column=0, sticky=EW, padx=5)
        ttk.Button(selection_frame, text="ফোল্ডার বাছুন", command=self.select_image_folder, bootstyle=OUTLINE).grid(row=3, column=1, padx=(10, 5))
        
        # এসইও রিনেম চেকবক্স
        rename_check = ttk.Checkbutton(
            selection_frame, 
            text=" টাইটেল দিয়ে ফাইলের নাম পরিবর্তন করুন (SEO Friendly)", 
            variable=self.rename_var, 
            bootstyle="success-round-toggle"
        )
        rename_check.grid(row=4, column=0, columnspan=2, sticky=W, padx=5, pady=(15, 0))
        
        selection_frame.columnconfigure(0, weight=1)
        
        self.apply_button = ttk.Button(main_frame, text=" ৩. মেটাডেটা প্রয়োগ করুন ", command=self.start_processing, bootstyle=SUCCESS, padding=10)
        self.apply_button.pack(fill=X, pady=(0, 20))
        
        status_frame = ttk.Labelframe(main_frame, text=" প্রসেসিং স্ট্যাটাস ", bootstyle=INFO, padding=15)
        status_frame.pack(fill=BOTH, expand=True)
        
        self.progress_bar = ttk.Progressbar(status_frame, bootstyle=SUCCESS, mode=DETERMINATE)
        self.progress_bar.pack(fill=X, pady=(5, 15))
        
        self.log_box = ScrolledText(status_frame, height=10, wrap=WORD, font=("Consolas", 9))
        self.log_box.pack(fill=BOTH, expand=True)
        self.log_box.text.config(state=DISABLED)
        
        self.status_label = ttk.Label(main_frame, text="প্রস্তুত", font=("Segoe UI", 9), bootstyle=INVERSE)
        self.status_label.pack(side=BOTTOM, fill=X, pady=(10, 0), ipady=3)

    def log(self, message):
        self.log_box.text.config(state=NORMAL)
        self.log_box.insert(END, message + "\n")
        self.log_box.see(END)
        self.log_box.text.config(state=DISABLED)

    def select_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv")])
        if path:
            self.csv_path.set(path)
            self.log(f"CSV ফাইল সিলেক্ট করা হয়েছে: {os.path.basename(path)}")
            self.status_label.config(text=f"CSV ফাইল লোড হয়েছে: {os.path.basename(path)}")

    def select_image_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.image_folder_path.set(path)
            self.log(f"ছবির ফোল্ডার সিলেক্ট করা হয়েছে: {path}")
            self.status_label.config(text=f"ছবির ফোল্ডার লোড হয়েছে।")

    # এসইও ফ্রেন্ডলি নাম তৈরি করার ফাংশন
    def generate_seo_filename(self, title):
        clean_title = re.sub(r'[\\/*?:"<>|]', "", str(title))
        clean_title = "-".join(clean_title.split()).lower()
        return clean_title

    def start_processing(self):
        if not self.csv_path.get() or not self.image_folder_path.get():
            messagebox.showerror("ত্রুটি", "অনুগ্রহ করে CSV ফাইল এবং ছবির ফোল্ডার উভয়ই সিলেক্ট করুন।")
            return
        
        self.apply_button.config(state=DISABLED)
        self.progress_bar['value'] = 0
        self.log_box.text.config(state=NORMAL)
        self.log_box.text.delete(1.0, END)
        self.log_box.text.config(state=DISABLED)
        
        self.processing_active = True
        threading.Thread(target=self.apply_metadata_logic, daemon=True).start()
        self.root.after(100, self.process_queue)

    def process_queue(self):
        try:
            msg = self.update_queue.get_nowait()
            msg_type, data = msg

            if msg_type == 'log':
                self.log(data)
            elif msg_type == 'progress':
                self.progress_bar['value'] = data
            elif msg_type == 'status':
                self.status_label.config(text=data)
            elif msg_type == 'max_progress':
                self.progress_bar.config(maximum=data)
            elif msg_type == 'finished':
                success, fail = data
                summary = f"\nপ্রসেসিং সম্পন্ন! সফলভাবে সম্পন্ন: {success}, ব্যর্থ হয়েছে: {fail}"
                self.log(summary)
                self.log("="*60)
                self.status_label.config(text=f"প্রসেসিং সম্পন্ন! সফল: {success}, ব্যর্থ: {fail}")
                messagebox.showinfo("সম্পন্ন", summary.strip())
                self.apply_button.config(state=NORMAL)
                self.processing_active = False
                return

        except queue.Empty:
            pass
        
        if self.processing_active:
            self.root.after(50, self.process_queue)

    def apply_metadata_logic(self):
        csv_file = self.csv_path.get()
        image_folder = self.image_folder_path.get()
        should_rename = self.rename_var.get()
        
        self.update_queue.put(('log', "="*60))
        self.update_queue.put(('log', "প্রসেসিং শুরু হচ্ছে... (v11.0 - JPG & PNG Supported)"))
        
        try:
            df = pd.read_csv(csv_file, encoding='utf-8-sig')
            df.columns = [c.strip().lower() for c in df.columns]

            total_files = len(df)
            self.update_queue.put(('max_progress', total_files))
            
            has_description = 'description' in df.columns
            if has_description:
                 self.update_queue.put(('log', f"CSV ফাইলে 'Description' কলাম পাওয়া গেছে।"))
            else:
                 self.update_queue.put(('log', f"সতর্কতা: CSV ফাইলে 'Description' কলাম পাওয়া যায়নি! টাইটেল ব্যবহার করা হবে।"))

            self.update_queue.put(('status', f"প্রসেসিং শুরু হচ্ছে... {total_files} টি ফাইল পাওয়া গেছে।"))
            
        except Exception as e:
            self.update_queue.put(('log', f"CSV ফাইল পড়তে সমস্যা: {e}"))
            self.update_queue.put(('finished', (0, 0)))
            return

        success_count, fail_count = 0, 0

        for index, row in df.iterrows():
            filename = row.get('filename')
            display_name = filename if filename and pd.notna(filename) else f"Row {index+1}"
            self.update_queue.put(('status', f"প্রসেস চলছে... ({index + 1}/{total_files}) - {display_name}"))

            if not filename or pd.isna(filename):
                self.update_queue.put(('log', f"সতর্কতা: সারি #{index+1} এ ফাইলের নাম নেই, এড়িয়ে যাওয়া হচ্ছে।"))
                fail_count += 1
                self.update_queue.put(('progress', index + 1))
                continue

            filename = str(filename).strip()
            image_path = os.path.join(image_folder, filename)
            
            # এখানে PNG যুক্ত করা হয়েছে
            if not os.path.exists(image_path) or not filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                self.update_queue.put(('log', f"সতর্কতা: '{filename}' ফাইলটি পাওয়া যায়নি অথবা এটি একটি সাপোর্টেড ছবি (JPG/PNG) নয়।"))
                fail_count += 1
                self.update_queue.put(('progress', index + 1))
                continue
            
            try:
                title = str(row.get('title', '')).strip()
                
                if has_description and pd.notna(row.get('description')):
                    description = str(row.get('description')).strip()
                else:
                    description = title 

                keywords_str = row.get('keywords')
                keywords_list = [k.strip() for k in str(keywords_str).split(',') if k.strip()] if pd.notna(keywords_str) else []

                # মেটাডেটা রাইটিং
                img = pyexiv2.Image(image_path)
                
                img.modify_xmp({
                    'Xmp.dc.title': title,
                    'Xmp.dc.description': description, 
                    'Xmp.dc.subject': keywords_list,
                    'Xmp.xmp.Rating': 5 
                })
                
                img.modify_iptc({
                    'Iptc.Application2.ObjectName': title,
                    'Iptc.Application2.Caption': description,
                    'Iptc.Application2.Keywords': keywords_list
                })
                
                img.modify_exif({
                    'Exif.Image.ImageDescription': description,
                    'Exif.Photo.UserComment': description, 
                    'Exif.Image.Rating': 5,
                    'Exif.Image.RatingPercent': 99
                })
                
                img.close()

                # ---------------- SEO রিনেম লজিক ----------------
                final_filename = filename
                if should_rename and title:
                    seo_name = self.generate_seo_filename(title)
                    if seo_name:
                        _, ext = os.path.splitext(filename)
                        new_filename = f"{seo_name}{ext}"
                        new_image_path = os.path.join(image_folder, new_filename)

                        # ডুপ্লিকেট নাম হ্যান্ডেল
                        counter = 1
                        while os.path.exists(new_image_path) and os.path.normcase(image_path) != os.path.normcase(new_image_path):
                            new_filename = f"{seo_name}-{counter}{ext}"
                            new_image_path = os.path.join(image_folder, new_filename)
                            counter += 1

                        # ফাইল রিনেম করা
                        if os.path.normcase(image_path) != os.path.normcase(new_image_path):
                            os.rename(image_path, new_image_path)
                            final_filename = new_filename

                # লগে PNG এর জন্য একটি সতর্কবার্তা দেখানো যাতে ইউজার ঘাবড়ে না যায়
                is_png = filename.lower().endswith('.png')
                png_note = " (বিঃদ্রঃ Windows Properties-এ PNG মেটা নাও দেখাতে পারে, তবে যুক্ত হয়েছে)" if is_png else ""

                if final_filename != filename:
                    self.update_queue.put(('log', f"সফল: '{filename}' -> '{final_filename}'{png_note}"))
                else:
                    self.update_queue.put(('log', f"সফল: '{filename}' (মেটাডেটা যুক্ত হয়েছে){png_note}"))
                
                success_count += 1

            except Exception as e:
                self.update_queue.put(('log', f"ত্রুটি: '{filename}' - {e}"))
                fail_count += 1
            
            self.update_queue.put(('progress', index + 1))
        
        self.update_queue.put(('finished', (success_count, fail_count)))

if __name__ == "__main__":
    root = ttk.Window(themename="litera")
    app = MetadataApp(root)
    root.mainloop()