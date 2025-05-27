import pymysql
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from bs4 import BeautifulSoup
from datetime import datetime
import time
import json
import traceback
import tempfile
from db import get_connection

# Initialize to None to prevent NameError in finally block
conn = None
cursor = None
driver = None

def log_error(error_message):
    with open("scraper_errors.log", "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {error_message}\n")

def ensure_connection_alive():
    global conn, cursor
    try:
        conn.ping(reconnect=True)
    except:
        conn = get_connection()
        cursor = conn.cursor()

try:
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    temp_profile_dir = tempfile.mkdtemp()
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-extensions")
    options.add_argument("--remote-debugging-port=9222")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--start-maximized")
    options.add_argument(f"--user-data-dir={temp_profile_dir}")

    driver = webdriver.Chrome(options=options)

    def get_total_pages():
        soup = BeautifulSoup(driver.page_source, "html.parser")
        pagination = soup.select("ul.pagination li a")
        page_numbers = [int(a.text.strip()) for a in pagination if a.text.strip().isdigit()]
        max_pages = max(page_numbers) if page_numbers else 1
        print(f"Total pages found: {max_pages}")
        return max_pages

    def get_value(soup, label):
        try:
            label_elem = soup.find("p", class_="font-bold", string=lambda t: t and label in t)
            if label_elem:
                value_elem = label_elem.find_next_sibling("p", class_="font-medium")
                return value_elem.get_text(strip=True) if value_elem else ""
        except:
            return ""
        return ""

    def extract_dates(soup, label):
        result = {"from": "", "to": ""}
        section = soup.find("p", class_="font-bold", string=lambda s: s and label in s)
        if section:
            text = section.find_next_sibling("p").get_text()
            parts = text.replace("Mula :", "").replace("Tamat :", "").split()
            if len(parts) >= 6:
                result["from"] = " ".join(parts[:3])
                result["to"] = " ".join(parts[3:])
        return result

    def scrape_project(link):
        try:
            driver.get(link)
            time.sleep(3)
            soup = BeautifulSoup(driver.page_source, "html.parser")

            data = {
                "license_number": get_value(soup, "No. Lesen"),
                "license_valid_from": "",
                "license_valid_to": "",
                "developer_name": get_value(soup, "Nama Pemaju"),
                "developer_code": get_value(soup, "Kod Pemaju"),
                "phone": get_value(soup, "No. Telefon"),
                "email": get_value(soup, "Emel"),
                "website": get_value(soup, "Laman Web"),
                "registered_address": get_value(soup, "Alamat Daftar"),
                "business_address": get_value(soup, "Alamat Perniagaan"),
                "permit_number": get_value(soup, "No. Permit Iklan dan Jualan"),
                "permit_valid_from": "",
                "permit_valid_to": "",
                "project_name": get_value(soup, "Nama Projek"),
                "district": get_value(soup, "Daerah Projek"),
                "project_code": get_value(soup, "Kod Projek"),
                "state": get_value(soup, "Negeri Projek"),
                "agreement_type": "",
                "original_construction_period": "",
                "first_pjb_date": "",
                "first_vp_date": "",
                "vp_amendment": "",
                "extension_approved": "",
                "new_construction_period": "",
                "new_vp_date": "",
                "development_info": "",
                "overall_status": "",
                "unit_detail_url": ""
            }

            data.update({
                "license_valid_from": extract_dates(soup, "Tarikh Sah Laku Lesen")["from"],
                "license_valid_to": extract_dates(soup, "Tarikh Sah Laku Lesen")["to"],
                "permit_valid_from": extract_dates(soup, "Tarikh Sah Laku Permit Terkini")["from"],
                "permit_valid_to": extract_dates(soup, "Tarikh Sah Laku Permit Terkini")["to"]
            })

            agreement_map = {
                "Jenis Perjanjian": "agreement_type",
                "Tempoh Pembinaan Asal": "original_construction_period",
                "Tarikh PJB Pertama": "first_pjb_date",
                "Tarikh Penyerahan Pemilikan Kosong Mengikut PJB Pertama": "first_vp_date",
                "Pindaan Tempoh Masa Untuk Penyerahan": "vp_amendment",
                "Tempoh Tambahan Diluluskan": "extension_approved",
                "Tempoh Pembinaan Baharu": "new_construction_period",
                "Tarikh Penyerahan Baharu Pemilikan Kosong Mengikut PJB Pertama": "new_vp_date"
            }

            for tr in soup.select("table.agreement-table tr"):
                tds = tr.find_all("td")
                if len(tds) >= 4:
                    label = tds[1].get_text(strip=True)
                    value = tds[3].get_text(strip=True)
                    key = agreement_map.get(label)
                    if key:
                        data[key] = value

            info_table = soup.find("table", style=lambda s: s and "width: 40%" in s)
            if info_table:
                for tr in info_table.find_all("tr"):
                    cols = tr.find_all("td")
                    if len(cols) == 3:
                        label = cols[0].get_text(strip=True).lower()
                        value = cols[2].get_text(strip=True)
                        if "maklumat pembangunan" in label:
                            data["development_info"] = value
                        elif "status keseluruhan" in label:
                            data["overall_status"] = value

            unit_detail = soup.find("a", href=lambda h: h and "/unit-project-swasta/" in h)
            if unit_detail:
                data["unit_detail_url"] = unit_detail["href"]

            ensure_connection_alive()
            cursor.execute("SELECT id FROM project_details WHERE project_code = %s", (data["project_code"],))
            existing = cursor.fetchone()

            if existing:
                project_id = existing[0]
                ensure_connection_alive()
                cursor.execute("DELETE FROM project_units_summary WHERE project_id = %s", (project_id,))
                cursor.execute("DELETE FROM project_unit_box_view WHERE project_id = %s", (project_id,))
            else:
                ensure_connection_alive()
                cursor.execute("""
                    INSERT INTO project_details (
                        license_number, license_valid_from, license_valid_to, developer_name,
                        developer_code, phone, email, website, registered_address, business_address,
                        permit_number, permit_valid_from, permit_valid_to, project_name, district,
                        project_code, state, agreement_type, original_construction_period,
                        first_pjb_date, first_vp_date, vp_amendment, extension_approved,
                        new_construction_period, new_vp_date, development_info, overall_status,
                        unit_detail_url, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                              %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                              %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, tuple(data.values()) + (now, now))
                project_id = cursor.lastrowid

            for row in soup.select("table tbody.bg-teduh-mid.bg-opacity-25 tr"):
                cols = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(cols) == 12:
                    ensure_connection_alive()
                    cursor.execute("""
                        INSERT INTO project_units_summary (
                            project_id, house_type, floors, rooms, toilets, built_up_area,
                            unit_count, min_price, max_price, actual_percentage,
                            component_status, ccc_date, vp_date, created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        project_id, *cols, now, now
                    ))

            if data["unit_detail_url"]:
                driver.get(data["unit_detail_url"])
                time.sleep(5)
                box_soup = BeautifulSoup(driver.page_source, "html.parser")
                for box in box_soup.select("div.unit-box"):
                    tooltip_json = box.get("data-tooltip")
                    if tooltip_json:
                        parsed = json.loads(tooltip_json.replace("&quot;", '"'))
                        ensure_connection_alive()
                        cursor.execute("""
                            INSERT INTO project_unit_box_view (
                                project_id, no_unit, no_pt_lot_plot, kuota_bumi,
                                harga_jualan, harga_spjb, status_jualan, created_at, updated_at
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            project_id,
                            parsed.get("No Unit", ""),
                            parsed.get("No PT/Lot/Plot", ""),
                            parsed.get("Kuota Bumi", ""),
                            parsed.get("Harga Jualan", ""),
                            parsed.get("Harga SPJB", ""),
                            parsed.get("Status Jualan", ""),
                            now, now
                        ))
        except Exception as e:
            log_error(f"Error scraping project {link}:\n{str(e)}\n{traceback.format_exc()}")

    driver.get("https://teduh.kpkt.gov.my/project-swasta")
    time.sleep(10)
    Select(driver.find_element(By.ID, "state")).select_by_value("14")
    time.sleep(5)
    driver.find_element(By.CSS_SELECTOR, "button.cari-button").click()
    time.sleep(5)

    for page in range(1, get_total_pages() + 1):
        print(f"Scraping page {page}")
        driver.get(f"https://teduh.kpkt.gov.my/project-swasta?page={page}")
        time.sleep(3)
        soup = BeautifulSoup(driver.page_source, "html.parser")
        for row in soup.select("table tbody tr"):
            try:
                cols = row.find_all("td")
                if len(cols) >= 7:
                    detail_url = cols[6].find("a")["href"]
                    scrape_project(detail_url)
                    ensure_connection_alive()
                    conn.commit()
            except Exception as e:
                log_error(f"Error scraping row on page {page}:\n{str(e)}\n{traceback.format_exc()}")

except Exception as e:
    log_error(f"Critical script error:\n{str(e)}\n{traceback.format_exc()}")

finally:
    if cursor:
        cursor.close()
    if conn:
        conn.close()
    if driver:
        driver.quit()
    print("\u2705 Monthly scrape completed with full project, summary, and unit box view data.")