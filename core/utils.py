import os
from fpdf import FPDF
from datetime import datetime

class CertificateGenerator:
    def __init__(self):
        self.temp_dir = "temp_certs"
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir)

    def generate(self, user_full_name, unit_title, date_str=None):
        if not date_str:
            date_str = datetime.now().strftime("%d.%m.%Y")
            
        pdf = FPDF(orientation="landscape", format="A4")
        pdf.add_page()
        
        # Oddiy border
        pdf.set_line_width(2)
        pdf.set_draw_color(50, 50, 150)
        pdf.rect(10, 10, 277, 190)
        
        # Sarlavha
        pdf.set_font("helvetica", "B", 45)
        pdf.set_text_color(30, 30, 100)
        pdf.set_y(40)
        pdf.cell(0, 20, "SERTIFIKAT", ln=True, align="C")
        
        pdf.ln(10)
        pdf.set_font("helvetica", "", 20)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(0, 10, "Ushbu sertifikat egasi:", ln=True, align="C")
        
        pdf.ln(10)
        # Ism-sharif (Uzbek harflari o'rniga dars nomini chiroyliroq chiqarish uchun oddiy font)
        # Eslatma: fpdf2 da o'zbek harflari (o', g') uchun maxsus font kerak bo'ladi.
        # Hozircha inglizcha harflar bilan cheklanamiz yoki Unicode font qo'shamiz.
        pdf.set_font("helvetica", "B", 35)
        pdf.set_text_color(180, 0, 0)
        pdf.cell(0, 20, user_full_name, ln=True, align="C")
        
        pdf.ln(10)
        pdf.set_font("helvetica", "", 18)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(0, 10, f"'{unit_title}' mavzusidagi barcha testlarni", ln=True, align="C")
        pdf.cell(0, 10, "muvaffaqiyatli yakunlagani uchun taqdirlandi.", ln=True, align="C")
        
        pdf.set_y(170)
        pdf.set_font("helvetica", "I", 12)
        pdf.cell(0, 10, f"Sana: {date_str}", ln=True, align="C")
        
        safe_name = user_full_name.replace(" ", "_").replace("'", "")
        file_path = os.path.join(self.temp_dir, f"cert_{safe_name}_{int(datetime.now().timestamp())}.pdf")
        pdf.output(file_path)
        return file_path
