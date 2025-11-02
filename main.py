import os
import re
import json
import time
import threading
import webbrowser
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import pandas as pd
import requests


SETTINGS_PATH = os.path.join(os.path.expanduser("~"), ".shopee_bestseller_settings.json")


@dataclass
class Product:
    title: str
    itemid: int
    shopid: int
    shop_name: Optional[str]
    price: float
    price_min: float
    price_max: float
    currency: str
    historical_sold: int
    sold_recent: Optional[int]
    rating: float
    rating_count: int
    stock: int
    url: str
    query: Optional[str] = None  # which keyword/query produced this row


class ShopeeClient:
    def __init__(self, domain="shopee.co.th", user_agent: Optional[str] = None, timeout: int = 20, delay: float = 0.8, stop_event: Optional[threading.Event] = None):
        self.domain = domain
        self.base = f"https://{domain}"
        self.sess = requests.Session()
        self.sess.headers.update({
            "User-Agent": user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": self.base + "/",
            "Accept-Language": "th-TH,th;q=0.9,en-US;q=0.8,en;q=0.7"
        })
        self.timeout = timeout
        self.delay = delay
        self.stop_event = stop_event or threading.Event()

    def _get(self, url: str, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(6):
            if self.stop_event.is_set():
                return {}
            try:
                r = self.sess.get(url, params=params, timeout=self.timeout)
                if r.status_code == 429:
                    time.sleep(self.delay * (attempt + 1) * 2)
                    continue
                r.raise_for_status()
                return r.json()
            except requests.RequestException:
                if attempt >= 5:
                    raise
                time.sleep(self.delay * (attempt + 1))
        return {}

    def search(self, keyword: str, page: int = 0, page_size: int = 60, by: str = "sales", order: str = "desc",
               price_min: Optional[int] = None, price_max: Optional[int] = None, category_id: Optional[int] = None) -> Dict[str, Any]:
        url = f"{self.base}/api/v4/search/search_items"
        params: Dict[str, Any] = {
            "by": by,
            "keyword": keyword,
            "limit": page_size,
            "newest": page * page_size,
            "order": order,
            "page_type": "search",
            "scenario": "PAGE_GLOBAL_SEARCH",
            "version": 2
        }
        if price_min is not None:
            params["price_min"] = price_min
        if price_max is not None:
            params["price_max"] = price_max
        if category_id is not None:
            params["match_id"] = category_id
            params["page_type"] = "search"
        return self._get(url, params=params)

    def shop_search(self, shopid: int, page: int = 0, page_size: int = 60, by: str = "sales", order: str = "desc") -> Dict[str, Any]:
        url = f"{self.base}/api/v4/search/search_items"
        params = {
            "by": by,
            "limit": page_size,
            "newest": page * page_size,
            "order": order,
            "page_type": "shop",
            "shopid": shopid,
            "version": 2
        }
        return self._get(url, params=params)

    def get_shop_info(self, shopid: int) -> Optional[str]:
        url = f"{self.base}/api/v4/shop/get_shop_detail"
        params = {"shopid": shopid}
        try:
            data = self._get(url, params)
            if isinstance(data, dict):
                return data.get("data", {}).get("name")
        except Exception:
            pass
        return None

    @staticmethod
    def _price_divisor(v: int) -> float:
        if v and v > 100000:
            return 100000.0
        return 100.0

    def to_product(self, raw: Dict[str, Any], query: Optional[str] = None) -> Product:
        itemid = raw.get("itemid") or 0
        shopid = raw.get("shopid") or 0

        price_raw = raw.get("price") or 0
        price_min_raw = raw.get("price_min") or price_raw
        price_max_raw = raw.get("price_max") or price_raw
        div = self._price_divisor(max(price_raw, price_min_raw, price_max_raw))

        def to_float(v): return float(v) / div if v else 0.0

        price = to_float(price_raw)
        price_min = to_float(price_min_raw)
        price_max = to_float(price_max_raw)

        currency = raw.get("currency") or ""
        hist_sold = raw.get("historical_sold") or 0
        sold_recent = raw.get("sold")

        rating_info = raw.get("item_rating") or {}
        rating = float(rating_info.get("rating_star") or 0)
        rating_count = int(sum(rating_info.get("rating_count") or [0]*6))
        stock = raw.get("stock") or 0

        name = raw.get("name") or ""
        url = f"{self.base}/product/{shopid}/{itemid}"

        return Product(
            title=name,
            itemid=itemid,
            shopid=shopid,
            shop_name=None,
            price=price,
            price_min=price_min,
            price_max=price_max,
            currency=currency,
            historical_sold=hist_sold,
            sold_recent=sold_recent,
            rating=rating,
            rating_count=rating_count,
            stock=stock,
            url=url,
            query=query
        )

    def fetch_best_sellers(
        self,
        keyword: Optional[str],
        max_pages: int = 3,
        min_sold: int = 0,
        fetch_shop_names: bool = True,
        price_min: Optional[int] = None,
        price_max: Optional[int] = None,
        category_id: Optional[int] = None,
        shopid: Optional[int] = None,
        query_label: Optional[str] = None
    ) -> List[Product]:
        all_items: List[Product] = []
        for page in range(max_pages):
            if self.stop_event.is_set():
                break
            if shopid:
                data = self.shop_search(shopid=shopid, page=page)
            else:
                data = self.search(keyword or "", page=page, price_min=price_min, price_max=price_max, category_id=category_id)
            items = (data.get("items") or []) if isinstance(data, dict) else []
            if not items:
                break
            for it in items:
                raw = it.get("item_basic") if isinstance(it, dict) and "item_basic" in it else it
                if not isinstance(raw, dict):
                    continue
                p = self.to_product(raw, query=query_label)
                if p.historical_sold >= min_sold:
                    all_items.append(p)
            time.sleep(self.delay)

        if fetch_shop_names and all_items and not self.stop_event.is_set():
            unique_shopids = sorted(set(p.shopid for p in all_items))
            cache: Dict[int, str] = {}
            for sid in unique_shopids:
                if self.stop_event.is_set():
                    break
                cache[sid] = self.get_shop_info(sid) or ""
                time.sleep(0.2)
            for p in all_items:
                p.shop_name = cache.get(p.shopid) or None

        all_items.sort(key=lambda x: (x.historical_sold, x.sold_recent or 0), reverse=True)
        return all_items


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Shopee Best-Seller Checker (Unofficial)")
        self.geometry("940x640")
        self.resizable(False, False)

        self.stop_event = threading.Event()

        self.domain_var = tk.StringVar(value="shopee.co.th")
        self.mode_var = tk.StringVar(value="keyword")  # 'keyword' or 'shop'
        self.keyword_var = tk.StringVar()
        self.shop_input_var = tk.StringVar()

        self.pages_var = tk.IntVar(value=3)
        self.min_sold_var = tk.IntVar(value=0)
        self.fetch_shop_var = tk.BooleanVar(value=True)

        self.price_min_var = tk.StringVar(value="")
        self.price_max_var = tk.StringVar(value="")
        self.category_var = tk.StringVar(value="")

        self.batch_keywords_var = tk.BooleanVar(value=False)

        self.status_var = tk.StringVar(value="พร้อมใช้งาน")
        self.progress_var = tk.DoubleVar(value=0.0)

        self._build_ui()
        self._load_settings()

        self.client: Optional[ShopeeClient] = None
        self.results: List[Product] = []

    def _build_ui(self):
        pad = {"padx": 8, "pady": 6}
        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, **pad)

        row = 0
        ttk.Label(frm, text="โดเมนประเทศ:").grid(row=row, column=0, sticky="e")
        domain_cb = ttk.Combobox(frm, textvariable=self.domain_var, values=[
            "shopee.co.th", "shopee.sg", "shopee.vn", "shopee.co.id", "shopee.com.my", "shopee.ph",
            "shopee.tw", "shopee.br", "shopee.com.mx", "shopee.cl", "shopee.com.co"
        ], state="readonly", width=22)
        domain_cb.grid(row=row, column=1, sticky="w")

        ttk.Label(frm, text="โหมดค้นหา:").grid(row=row, column=2, sticky="e")
        mode_cb = ttk.Combobox(frm, textvariable=self.mode_var, values=["keyword", "shop"], state="readonly", width=12)
        mode_cb.grid(row=row, column=3, sticky="w")

        row += 1
        ttk.Checkbutton(frm, text="โหมดหลายคีย์เวิร์ด (พิมพ์ทีละบรรทัด)", variable=self.batch_keywords_var, command=self._toggle_batch).grid(row=row, column=0, columnspan=2, sticky="w")

        # Keyword input
        self.keyword_label = ttk.Label(frm, text="Keyword:")
        self.keyword_label.grid(row=row, column=2, sticky="e")
        self.keyword_entry = ttk.Entry(frm, textvariable=self.keyword_var, width=28)
        self.keyword_entry.grid(row=row, column=3, sticky="w")

        row += 1
        # Batch textbox (hidden by default)
        self.batch_text = tk.Text(frm, width=40, height=6)
        self.batch_text.grid(row=row, column=0, columnspan=2, sticky="we")
        self.batch_text.grid_remove()

        # Shop input
        ttk.Label(frm, text="Shop ID/URL:").grid(row=row, column=2, sticky="e")
        ttk.Entry(frm, textvariable=self.shop_input_var, width=28).grid(row=row, column=3, sticky="w")

        row += 1
        ttk.Label(frm, text="จำนวนหน้า (สูงสุด):").grid(row=row, column=0, sticky="e")
        ttk.Spinbox(frm, from_=1, to=50, textvariable=self.pages_var, width=10).grid(row=row, column=1, sticky="w")

        ttk.Label(frm, text="คัดกรองยอดขายขั้นต่ำ:").grid(row=row, column=2, sticky="e")
        ttk.Spinbox(frm, from_=0, to=1_000_000, increment=50, textvariable=self.min_sold_var, width=12).grid(row=row, column=3, sticky="w")

        row += 1
        ttk.Label(frm, text="ช่วงราคา (ขั้นต่ำ-สูงสุด):").grid(row=row, column=0, sticky="e")
        ttk.Entry(frm, textvariable=self.price_min_var, width=12).grid(row=row, column=1, sticky="w")
        ttk.Entry(frm, textvariable=self.price_max_var, width=12).grid(row=row, column=2, sticky="w")

        ttk.Label(frm, text="Category ID/URL:").grid(row=row, column=3, sticky="e")
        self.category_entry = ttk.Entry(frm, textvariable=self.category_var, width=28)
        self.category_entry.grid(row=row, column=4, sticky="w")
        frm.grid_columnconfigure(4, weight=1)

        row += 1
        ttk.Checkbutton(frm, text="ดึงชื่อร้านค้า", variable=self.fetch_shop_var).grid(row=row, column=0, columnspan=2, sticky="w")

        row += 1
        ttk.Button(frm, text="ดึงข้อมูล", command=self.on_fetch).grid(row=row, column=0, sticky="we", **pad)
        ttk.Button(frm, text="หยุด", command=self.on_stop).grid(row=row, column=1, sticky="we", **pad)
        ttk.Button(frm, text="เปิดลิงก์สินค้า", command=self.on_open_link).grid(row=row, column=2, sticky="we", **pad)
        ttk.Button(frm, text="บันทึกเป็น Excel/CSV", command=self.on_export).grid(row=row, column=3, sticky="we", **pad)
        ttk.Button(frm, text="ช่วยเหลือ", command=self.on_help).grid(row=row, column=4, sticky="we", **pad)

        row += 1
        ttk.Separator(frm).grid(row=row, column=0, columnspan=5, sticky="ew", pady=4)

        row += 1
        self.tree = ttk.Treeview(frm, columns=("title","shop","sold","price","rating","url","query"), show="headings", height=16)
        self.tree.heading("title", text="สินค้า")
        self.tree.heading("shop", text="ร้านค้า")
        self.tree.heading("sold", text="ยอดขาย (สะสม)")
        self.tree.heading("price", text="ราคา")
        self.tree.heading("rating", text="เรตติ้ง/รีวิว")
        self.tree.heading("url", text="ลิงก์")
        self.tree.heading("query", text="คีย์เวิร์ด/ชุดค้นหา")
        self.tree.column("title", width=300)
        self.tree.column("shop", width=160)
        self.tree.column("sold", width=110, anchor="e")
        self.tree.column("price", width=110, anchor="e")
        self.tree.column("rating", width=110, anchor="center")
        self.tree.column("url", width=250)
        self.tree.column("query", width=160)
        self.tree.grid(row=row, column=0, columnspan=5, sticky="nsew")

        row += 1
        ttk.Label(frm, textvariable=self.status_var).grid(row=row, column=0, sticky="w", columnspan=2)
        ttk.Progressbar(frm, variable=self.progress_var, maximum=100).grid(row=row, column=2, columnspan=3, sticky="ew")

        for c in range(5):
            frm.grid_columnconfigure(c, weight=1)

    def _toggle_batch(self):
        if self.batch_keywords_var.get():
            self.batch_text.grid()
            self.keyword_label.config(text="Keyword (สำรอง):")
        else:
            self.batch_text.grid_remove()
            self.keyword_label.config(text="Keyword:")

    def _save_settings(self):
        data = {
            "domain": self.domain_var.get(),
            "mode": self.mode_var.get(),
            "keyword": self.keyword_var.get(),
            "pages": self.pages_var.get(),
            "min_sold": self.min_sold_var.get(),
            "fetch_shop": self.fetch_shop_var.get(),
            "price_min": self.price_min_var.get(),
            "price_max": self.price_max_var.get(),
            "category": self.category_var.get(),
            "batch": self.batch_keywords_var.get(),
            "shop_input": self.shop_input_var.get(),
            "batch_text": self.batch_text.get("1.0", "end").strip() if self.batch_keywords_var.get() else ""
        }
        try:
            with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_settings(self):
        try:
            if os.path.exists(SETTINGS_PATH):
                with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.domain_var.set(data.get("domain", self.domain_var.get()))
                self.mode_var.set(data.get("mode", self.mode_var.get()))
                self.keyword_var.set(data.get("keyword", ""))
                self.pages_var.set(int(data.get("pages", 3)))
                self.min_sold_var.set(int(data.get("min_sold", 0)))
                self.fetch_shop_var.set(bool(data.get("fetch_shop", True)))
                self.price_min_var.set(str(data.get("price_min", "")))
                self.price_max_var.set(str(data.get("price_max", "")))
                self.category_var.set(str(data.get("category", "")))
                self.batch_keywords_var.set(bool(data.get("batch", False)))
                self.shop_input_var.set(str(data.get("shop_input","")))
                if self.batch_keywords_var.get():
                    self.batch_text.grid()
                    self.batch_text.delete("1.0", "end")
                    self.batch_text.insert("1.0", data.get("batch_text", ""))
            self._toggle_batch()
        except Exception:
            pass

    @staticmethod
    def parse_shopid(s: str) -> Optional[int]:
        s = (s or "").strip()
        if not s:
            return None
        if s.isdigit():
            return int(s)
        m = re.search(r"/shop/(\d+)", s)
        if m:
            return int(m.group(1))
        m = re.search(r"(shopid|sellerid)=(\d+)", s, re.I)
        if m:
            return int(m.group(2))
        return None

    @staticmethod
    def parse_category_id(s: str) -> Optional[int]:
        s = (s or "").strip()
        if not s:
            return None
        if s.isdigit():
            return int(s)
        m = re.search(r"[._-]cat[._-]?(\d+)", s, re.I)
        if m:
            return int(m.group(1))
        m = re.search(r"(category|catid)=(\d+)", s, re.I)
        if m:
            return int(m.group(2))
        return None

    def on_help(self):
        messagebox.showinfo(
            "วิธีใช้",
            "• โหมดหลายคีย์เวิร์ด: ใส่คีย์เวิร์ดหลายบรรทัด โปรแกรมจะวนดึงและเพิ่มคอลัมน์ 'คีย์เวิร์ด/ชุดค้นหา'\n"
            "• ระบุ Category ได้ทั้งตัวเลข หรือวาง URL หมวดหมู่ (ตัวอย่างที่มี 'cat.12345' หรือ 'category=12345')\n"
            "• ปุ่มหยุด: ยกเลิกการดึงข้อมูลที่กำลังทำงานอยู่\n"
            "• เปิดลิงก์สินค้า: เลือกแถวในตารางแล้วกดเพื่อเปิดในเบราว์เซอร์\n"
        )

    def on_stop(self):
        self.stop_event.set()
        self.status_var.set("กำลังหยุด...")
        self.progress_var.set(0)

    def on_open_link(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("เปิดลิงก์", "กรุณาเลือกสินค้าที่ต้องการ")
            return
        vals = self.tree.item(sel[0], "values")
        url = vals[5] if len(vals) >= 6 else ""
        if url:
            webbrowser.open(url)

    def on_fetch(self):
        self._save_settings()
        self.stop_event.clear()

        domain = self.domain_var.get().strip() or "shopee.co.th"
        mode = self.mode_var.get()
        keyword = self.keyword_var.get().strip()
        shop_input = self.shop_input_var.get().strip()

        pages = int(self.pages_var.get())
        min_sold = int(self.min_sold_var.get())
        fetch_shop = bool(self.fetch_shop_var.get())

        price_min = self.price_min_var.get().strip()
        price_max = self.price_max_var.get().strip()
        cat = self.category_var.get().strip()

        price_min_i = int(price_min) if price_min.isdigit() else None
        price_max_i = int(price_max) if price_max.isdigit() else None
        cat_i = self.parse_category_id(cat)

        shopid = None
        if mode == "shop":
            shopid = self.parse_shopid(shop_input)
            if not shopid:
                messagebox.showwarning("แจ้งเตือน", "กรุณาระบุ Shop ID หรือ URL ร้านที่ถูกต้อง")
                return
        else:
            if not keyword and not self.batch_keywords_var.get():
                messagebox.showwarning("แจ้งเตือน", "กรุณากรอก keyword หรือใช้โหมดหลายคีย์เวิร์ด")
                return

        self.client = ShopeeClient(domain=domain, stop_event=self.stop_event)
        self.status_var.set("กำลังดึงข้อมูล...")
        self.progress_var.set(0)
        self.results.clear()
        self.tree.delete(*self.tree.get_children())
        self.update_idletasks()

        batch_list: List[str] = []
        if self.batch_keywords_var.get():
            raw = self.batch_text.get("1.0", "end").strip()
            batch_list = [line.strip() for line in raw.splitlines() if line.strip()]

        def worker():
            try:
                items_total: List[Product] = []
                if mode == "shop":
                    items = self.client.fetch_best_sellers(
                        keyword=None,
                        max_pages=pages,
                        min_sold=min_sold,
                        fetch_shop_names=fetch_shop,
                        price_min=price_min_i,
                        price_max=price_max_i,
                        category_id=cat_i,
                        shopid=shopid,
                        query_label=f"shop:{shopid}"
                    )
                    items_total.extend(items)
                else:
                    if batch_list:
                        for idx, kw in enumerate(batch_list, start=1):
                            if self.stop_event.is_set(): break
                            self.status_var.set(f"ดึงข้อมูล ({idx}/{len(batch_list)}) : {kw}")
                            items = self.client.fetch_best_sellers(
                                keyword=kw,
                                max_pages=pages,
                                min_sold=min_sold,
                                fetch_shop_names=fetch_shop,
                                price_min=price_min_i,
                                price_max=price_max_i,
                                category_id=cat_i,
                                shopid=None,
                                query_label=kw
                            )
                            items_total.extend(items)
                            self.after(0, lambda: self.progress_var.set((idx/len(batch_list))*100))
                    else:
                        items = self.client.fetch_best_sellers(
                            keyword=keyword,
                            max_pages=pages,
                            min_sold=min_sold,
                            fetch_shop_names=fetch_shop,
                            price_min=price_min_i,
                            price_max=price_max_i,
                            category_id=cat_i,
                            shopid=None,
                            query_label=keyword
                        )
                        items_total.extend(items)

                seen = set()
                deduped: List[Product] = []
                for p in items_total:
                    key = (p.shopid, p.itemid)
                    if key in seen: continue
                    seen.add(key)
                    deduped.append(p)

                self.results = deduped
                self.after(0, self._populate_table)
                self.after(0, lambda: self.status_var.set(f"พบ {len(deduped)} รายการ"))
                self.after(0, lambda: self.progress_var.set(100 if not self.stop_event.is_set() else 0))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("เกิดข้อผิดพลาด", str(e)))
                self.after(0, lambda: self.status_var.set("ล้มเหลว"))
                self.after(0, lambda: self.progress_var.set(0))

        threading.Thread(target=worker, daemon=True).start()

    def _populate_table(self):
        self.tree.delete(*self.tree.get_children())
        for p in self.results:
            price_text = f"{p.price_min:.2f} - {p.price_max:.2f} {p.currency}" if p.price_min != p.price_max else f"{p.price:.2f} {p.currency}"
            rating_text = f"{p.rating:.2f} / {p.rating_count} รีวิว" if p.rating_count else f"{p.rating:.2f}"
            self.tree.insert("", "end", values=(p.title, p.shop_name or "", f"{p.historical_sold:,}", price_text, rating_text, p.url, p.query or ""))

    def on_export(self):
        if not self.results:
            messagebox.showwarning("ยังไม่มีข้อมูล", "กรุณาดึงข้อมูลก่อน")
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel Workbook", "*.xlsx"), ("CSV", "*.csv")],
            title="บันทึกผลลัพธ์",
            initialfile="shopee_bestsellers.xlsx"
        )
        if not path:
            return

        df = pd.DataFrame([asdict(p) for p in self.results])
        try:
            if path.lower().endswith(".csv"):
                df.to_csv(path, index=False, encoding="utf-8-sig")
            else:
                df.to_excel(path, index=False)
            messagebox.showinfo("สำเร็จ", f"บันทึกไฟล์แล้ว:\n{path}")
        except Exception as e:
            messagebox.showerror("บันทึกล้มเหลว", str(e))


if __name__ == "__main__":
    try:
        App().mainloop()
    except KeyboardInterrupt:
        pass
