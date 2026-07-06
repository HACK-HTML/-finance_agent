"""Generate a simulated financial product prospectus PDF for RAG pipeline testing."""
from fpdf import FPDF
import os


class ProductPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(0, 71, 153)
        self.cell(0, 10, "Huaxia Wealth Management - Stable Growth 365 Prospectus", align="C",
                  new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(0, 71, 153)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(128)
        self.cell(0, 10, f"Page {self.page_no()} / Internal - Demo Only", align="C")


def build_product_doc():
    pdf = ProductPDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # Section 1: Product Overview
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(0, 71, 153)
    pdf.cell(0, 10, "1. Product Overview", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(40, 40, 40)
    pdf.multi_cell(0, 6,
        '"Huaxia Stable Growth 365" is a hybrid public wealth management product issued by '
        'Huaxia Bank Co., Ltd. The product primarily invests in fixed-income assets (min 60% '
        'allocation) supplemented by equity assets (max 30% allocation). It adopts a "defensive '
        'core + flexible satellite" strategy, aiming to deliver excess returns while preserving '
        'principal safety.\n\n'
        'Product Registration Code: C202404150001\n'
        'Issuer: Huaxia Bank Co., Ltd.\n'
        'Investment Manager: Huaxia Wealth Management Co., Ltd.\n'
        'Custodian Bank: China Construction Bank Corporation\n'
        'Subscription Period: January 10, 2025 - January 17, 2025\n'
        'Value Date: January 18, 2025\n'
        'Maturity Date: December 31, 2025\n'
        'Product Term: 347 days\n'
        'Operation Mode: Closed-end NAV-based\n'
        'Risk Rating: R2 (Conservative - suitable for conservative investors and above)'
    )
    pdf.ln(4)

    # Section 2: Fee Structure
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(0, 71, 153)
    pdf.cell(0, 10, "2. Fee Structure", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    col_w = [56, 52, 47, 35]
    headers = ["Fee Item", "Rate", "Charging Timing", "Notes"]
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(0, 71, 153)
    pdf.set_text_color(255, 255, 255)
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 8, h, border=1, fill=True, align="C")
    pdf.ln()

    fee_rows = [
        ["Subscription Fee", "0.30%", "Deducted at subscription", "Waived for >= 1M CNY"],
        ["Mgmt Fee (Fixed)", "0.60%/year", "Accrued daily, paid monthly", "Pre-deducted from NAV daily"],
        ["Custodian Fee", "0.05%/year", "Accrued daily, paid monthly", "Paid to custodian bank"],
        ["Mgmt Fee (Floating)", "20% of excess return", "Deducted at maturity", "On return above 4.0% benchmark"],
        ["Redemption Fee", "0.00%", "N/A", "Auto-redeemed at maturity, no fee"],
        ["Distribution Fee", "0.20%/year", "Accrued daily, paid monthly", "Paid to distribution channel"],
    ]
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(40, 40, 40)
    for i, row in enumerate(fee_rows):
        pdf.set_fill_color(245, 250, 255) if i % 2 == 0 else pdf.set_fill_color(255, 255, 255)
        for j, val in enumerate(row):
            align = "L" if j == 0 else "C"
            pdf.cell(col_w[j], 7, val, border=1, fill=True, align=align)
        pdf.ln()

    pdf.ln(2)
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(100, 100, 100)
    pdf.multi_cell(0, 5,
        "Fee Example: Assume an investor subscribes CNY 100,000 and holds to maturity. "
        "Fixed management fee is approx. CNY 600/year (accrued daily). If the product delivers "
        "5.2% annualized return at maturity, the excess over the 4.0% benchmark is 1.2%. "
        "Floating management fee = 100,000 x 1.2% x (347/365) x 20% = approx. CNY 228."
    )
    pdf.ln(4)

    # Section 3: Investment Scope
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(0, 71, 153)
    pdf.cell(0, 10, "3. Investment Scope & Asset Allocation", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(40, 40, 40)
    pdf.multi_cell(0, 6,
        "The product invests in the following asset classes with target allocation ranges:\n\n"
        "(A) Fixed-Income Assets (Target Allocation: 60% - 85%)\n"
        "  1. Government bonds, central bank bills, policy bank bonds - minimum 10%\n"
        "  2. Commercial bank bonds, corporate bonds, medium-term notes - minimum 20%\n"
        "  3. Standardized Asset-Backed Securities (ABS) - maximum 15%\n"
        "  4. Negotiated deposits, large-denomination CDs - minimum 10%\n\n"
        "(B) Equity Assets (Target Allocation: 0% - 30%)\n"
        "  1. A-share stocks (including preferred shares) - maximum 20%\n"
        "  2. Equity mutual funds - maximum 10%\n"
        "  3. This product does NOT invest in ST stocks, *ST stocks, or NEEQ stocks.\n\n"
        "(C) Liquid Assets (Target Allocation: 5% - 15%)\n"
        "  1. Bank deposits, money market funds, reverse repos (<= 7 days) - minimum 5%\n\n"
        "(D) Prohibited Investments\n"
        "  This product does NOT invest in offshore derivatives, unlisted equity, REITs, "
        "or any leveraged financial instruments."
    )
    pdf.ln(4)

    # Section 4: Performance Benchmark
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(0, 71, 153)
    pdf.cell(0, 10, "4. Performance Benchmark & Income Distribution", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(40, 40, 40)
    pdf.multi_cell(0, 6,
        "Performance Benchmark (Annualized): 4.0%\n\n"
        "Benchmark Calculation Basis: Based on the product's target asset allocation, assuming "
        "a bond portfolio yield of 3.2% and equity dividend + capital gain contribution of 0.8%, "
        "weighted to form the composite benchmark. The benchmark is a target the manager strives "
        "to exceed and does NOT constitute a guarantee of principal or return.\n\n"
        "Income Distribution Rules:\n"
        "  - This is a closed-end NAV-based product; no income distribution during the term.\n"
        "  - At maturity, all net income after fees belongs to the investor.\n"
        "  - If the unit NAV at maturity is below 1.0000 (i.e. principal loss), the manager "
        "shall refund 50% of the fixed management fee collected to the investor "
        "(see Section 8: Risk Protection)."
    )
    pdf.ln(4)

    # Section 5: Redemption Rules
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(0, 71, 153)
    pdf.cell(0, 10, "5. Redemption Rules & Liquidity Arrangements", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(40, 40, 40)
    pdf.multi_cell(0, 6,
        "(A) Normal Maturity Redemption\n"
        "  Within 3 business days after the maturity date (December 31, 2025), funds are "
        "automatically transferred to the investor's account. Redemption fee: 0.\n\n"
        "(B) Early Redemption (including urgent liquidity needs)\n"
        "  Early redemption is permitted under the following two circumstances:\n"
        "  1. If the investor urgently needs funds due to major illness, home purchase down "
        "payment, children's education expenses, etc., and obtains manager approval, early "
        "redemption may be processed on the last business day of each quarter end "
        "(March, June, September, December). An early redemption penalty of 0.50% is charged "
        "(deducted directly from the redemption proceeds), and funds arrive within 5-7 "
        "business days after the application is submitted.\n"
        "  2. During the subscription period (January 10-17, 2025), subscriptions may be "
        "cancelled unconditionally with a full refund and no fees.\n\n"
        "(C) Mass Redemption\n"
        "  If cumulative redemption applications on a single redemption date exceed 10% of "
        "total product units, this constitutes a mass redemption event. The manager may extend "
        "payment to 15 business days and allocate available redemption quota on a pro-rata basis."
    )
    pdf.ln(4)

    # Section 6: Risk Disclosure
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(0, 71, 153)
    pdf.cell(0, 10, "6. Risk Disclosure & Suitable Investor Profile", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(40, 40, 40)
    pdf.multi_cell(0, 6,
        "This product is rated R2 (Conservative). Key risks are as follows:\n\n"
        "  1. Interest Rate Risk: Bond prices move inversely to market interest rates. "
        "If the central bank raises rates, existing bond holdings may decline in value, "
        "potentially causing temporary NAV drawdowns.\n"
        "  2. Credit Risk: Issuers of corporate bonds and ABS in the portfolio may default, "
        "resulting in failure to pay principal or interest on time. To control credit risk, "
        "the product limits any single corporate bond to 3% of the portfolio and requires "
        "a minimum credit rating of AA+ for all bond investments.\n"
        "  3. Equity Market Volatility Risk: Equity asset prices are influenced by "
        "macroeconomics, policy, market sentiment, and other factors. Maximum drawdown is "
        "expected not to exceed 5%.\n"
        "  4. Liquidity Risk: This is a closed-end product. Redemption is generally not "
        "permitted during the term. Investors should ensure the invested funds will not be "
        "needed for the full 347 days.\n"
        "  5. Management Risk: Errors in asset allocation or security selection by the "
        "investment manager may adversely affect actual returns.\n\n"
        "Suitable Investor Profile:\n"
        "  This product is suitable for investors with risk rating R2 (Conservative) or above. "
        "Investors should meet the following criteria:\n"
        "  - Able to tolerate moderate NAV volatility (max drawdown <= 5%)\n"
        "  - No liquidity needs for the invested funds within 347 days\n"
        "  - Basic understanding of financial markets; understands that wealth management "
        "products do not guarantee principal or returns\n"
        "  - Possesses reasonable risk identification and judgment capability"
    )
    pdf.ln(4)

    # Section 7: Information Disclosure
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(0, 71, 153)
    pdf.cell(0, 10, "7. Information Disclosure & Investor Inquiry Channels", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(40, 40, 40)
    pdf.multi_cell(0, 6,
        "  1. The product's unit NAV is published every weekend. Investors may check it via "
        "the Huaxia Bank mobile banking app, internet banking, or any branch nationwide.\n"
        "  2. A quarterly asset operation report is published, disclosing asset allocation "
        "details and the top 10 bond/stock holdings as of the reporting date.\n"
        "  3. If an event occurs that materially affects the product's return or risk profile "
        "(e.g. bond rating downgrade, fee adjustment, early termination), the manager shall "
        "issue a temporary announcement within 3 business days.\n"
        "  4. For any questions about the product, investors may call the customer service "
        "hotline at 95577 (24/7 service)."
    )
    pdf.ln(4)

    # Section 8: Risk Protection
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(0, 71, 153)
    pdf.cell(0, 10, "8. Risk Protection Provisions", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(40, 40, 40)
    pdf.multi_cell(0, 6,
        "  1. If the unit NAV at maturity falls below 1.0000 (i.e. principal loss occurs), "
        "the manager commits to:\n"
        "     (a) Refund 50% of the fixed management fee collected to the investor;\n"
        "     (b) Not charge any floating management fee.\n"
        "  2. Huaxia Bank Co., Ltd. serves as the credit enhancement party for this product. "
        "If the investment manager fails to fulfill its management duties and causes material "
        "losses to investors, the issuing bank shall bear joint and several liability.\n"
        "  3. The product's raised funds are held in an independent custody account with China "
        "Construction Bank. Investment operations and fund settlement are fully segregated, "
        "preventing any risk of misappropriation by the manager."
    )
    pdf.ln(6)

    # Disclaimer
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(150, 150, 150)
    pdf.multi_cell(0, 4,
        "Disclaimer: This document is a simulated financial product prospectus created for "
        "system demonstration and testing purposes only. All institution names, product "
        "information, and figures are fictional and do not represent any real financial "
        "product or institution. Investors should NOT rely on this document for any "
        "actual financial decisions."
    )

    out = os.path.join(os.path.dirname(__file__),
                       "Huaxia_Stable_Growth_365_Prospectus.pdf")
    pdf.output(out)
    return out


if __name__ == "__main__":
    path = build_product_doc()
    print(f"PDF generated: {path}")
