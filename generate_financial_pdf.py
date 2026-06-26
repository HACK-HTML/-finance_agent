"""Generate a simulated financial report PDF."""
from fpdf import FPDF
import os

class FinancialPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(0, 51, 102)
        self.cell(0, 10, "ABC Technology Inc. - 2024 Annual Financial Report", align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(0, 51, 102)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(128)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

def build_report():
    pdf = FinancialPDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # Section 1 — Summary
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 10, "1. Executive Summary", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(40, 40, 40)
    pdf.multi_cell(0, 6,
        "ABC Technology Inc. reported total revenue of CNY 8.52 billion for the fiscal year ended "
        "December 31, 2024, representing a 16.3% year-over-year increase (FY2023: CNY 7.33 billion). "
        "Net profit attributable to shareholders reached CNY 1.24 billion, up 22.7% YoY. "
        "The strong performance was primarily driven by growth in cloud services (+34.2% YoY) and "
        "enterprise SaaS subscriptions (+28.1% YoY). Gross margin improved from 58.2% to 61.4%, "
        "reflecting a favorable product mix shift toward higher-margin recurring revenue streams."
    )
    pdf.ln(4)

    # Section 2 — Key Metrics
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 10, "2. Key Financial Metrics (CNY Million)", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    col_w = [70, 40, 40, 40]
    headers = ["Metric", "FY2024", "FY2023", "YoY %"]
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(0, 51, 102)
    pdf.set_text_color(255, 255, 255)
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 8, h, border=1, fill=True, align="C")
    pdf.ln()

    rows = [
        ["Revenue",              "8,520",  "7,330",  "+16.3%"],
        ["Cost of Revenue",      "3,288",  "3,064",  "+7.3%"],
        ["Gross Profit",          "5,232",  "4,266",  "+22.6%"],
        ["Gross Margin",          "61.4%",  "58.2%",  "+3.2pp"],
        ["Operating Expenses",   "3,108",  "2,815",  "+10.4%"],
        ["  R&D",                "1,704",  "1,466",  "+16.2%"],
        ["  Sales & Marketing",  "1,022",  "935",    "+9.3%"],
        ["  G&A",               "382",    "414",    "-7.7%"],
        ["Operating Income",     "2,124",  "1,451",  "+46.4%"],
        ["Net Income",           "1,240",  "1,011",  "+22.7%"],
        ["EPS (CNY)",            "3.72",   "3.04",   "+22.4%"],
    ]
    pdf.set_font("Helvetica", "", 9)
    for row in rows:
        if row[0].startswith("  "):
            pdf.set_text_color(100, 100, 100)
        else:
            pdf.set_text_color(40, 40, 40)
        pdf.set_fill_color(250, 250, 250) if rows.index(row) % 2 == 0 else pdf.set_fill_color(255, 255, 255)
        for i, val in enumerate(row):
            align = "L" if i == 0 else "C"
            pdf.cell(col_w[i], 7, val, border=1, fill=True, align=align)
        pdf.ln()
    pdf.ln(4)

    # Section 3 — Revenue Breakdown
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 10, "3. Revenue by Segment", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    col_w2 = [70, 40, 40, 40]
    headers2 = ["Segment", "FY2024", "FY2023", "YoY %"]
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(0, 51, 102)
    pdf.set_text_color(255, 255, 255)
    for i, h in enumerate(headers2):
        pdf.cell(col_w2[i], 8, h, border=1, fill=True, align="C")
    pdf.ln()

    seg_rows = [
        ["Cloud Services",       "3,408", "2,540", "+34.2%"],
        ["Enterprise SaaS",      "2,556", "1,995", "+28.1%"],
        ["Hardware & IoT",       "1,704", "1,833", "-7.0%"],
        ["Professional Services", "852",  "962",  "-11.4%"],
    ]
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(40, 40, 40)
    for i, row in enumerate(seg_rows):
        pdf.set_fill_color(245, 250, 255) if i % 2 == 0 else pdf.set_fill_color(255, 255, 255)
        for j, val in enumerate(row):
            align = "L" if j == 0 else "C"
            pdf.cell(col_w2[j], 7, val, border=1, fill=True, align=align)
        pdf.ln()
    pdf.ln(4)

    # Section 4 — Balance Sheet Highlights
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 10, "4. Balance Sheet Highlights (CNY Million)", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    col_w3 = [60, 45, 45]
    headers3 = ["Item", "Dec 31, 2024", "Dec 31, 2023"]
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(0, 51, 102)
    pdf.set_text_color(255, 255, 255)
    for i, h in enumerate(headers3):
        pdf.cell(col_w3[i], 8, h, border=1, fill=True, align="C")
    pdf.ln()

    bs_rows = [
        ["Cash & Equivalents",     "4,260", "3,520"],
        ["Total Assets",           "15,340", "12,880"],
        ["Total Liabilities",      "5,369", "4,764"],
        ["Shareholders' Equity",   "9,971", "8,116"],
        ["Debt-to-Equity Ratio",   "0.32x", "0.38x"],
    ]
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(40, 40, 40)
    for i, row in enumerate(bs_rows):
        pdf.set_fill_color(250, 250, 250) if i % 2 == 0 else pdf.set_fill_color(255, 255, 255)
        for j, val in enumerate(row):
            align = "L" if j == 0 else "C"
            pdf.cell(col_w3[j], 7, val, border=1, fill=True, align=align)
        pdf.ln()
    pdf.ln(4)

    # Section 5 — Outlook
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 10, "5. 2025 Outlook & Guidance", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(40, 40, 40)
    pdf.multi_cell(0, 6,
        "For FY2025, the Company provides the following guidance:\n"
        "- Total revenue is expected to be in the range of CNY 9.8 - 10.2 billion (15% - 20% YoY growth).\n"
        "- Cloud services revenue is projected to exceed CNY 4.5 billion.\n"
        "- Gross margin is expected to remain above 60%.\n"
        "- R&D investment will increase to approximately 22% of revenue, focused on AI/ML platform capabilities.\n"
        "- Capital expenditure of CNY 1.2 - 1.5 billion planned for data center expansion.\n\n"
        "Key risks include: macroeconomic uncertainty in domestic markets, intensifying competition in the "
        "enterprise SaaS space, and regulatory changes in data governance. Management remains confident in "
        "achieving sustained double-digit revenue growth through continued product innovation and market expansion."
    )
    pdf.ln(6)

    # Disclaimer
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(150, 150, 150)
    pdf.multi_cell(0, 4,
        "Disclaimer: This document is a simulated financial report generated for demonstration purposes only. "
        "All figures, company names, and data are fictional and do not represent any real entity. "
        "This document should not be used for any investment, accounting, or legal decisions."
    )

    out = os.path.join(os.path.dirname(__file__), "ABC_Tech_2024_Annual_Report.pdf")
    pdf.output(out)
    return out

if __name__ == "__main__":
    path = build_report()
    print(f"PDF generated: {path}")
