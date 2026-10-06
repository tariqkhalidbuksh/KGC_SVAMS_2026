import os
import io
import time
from datetime import datetime
from PIL import Image as PILImage

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, KeepTogether, HRFlowable
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

import config

def _safe_rl_image(img_rel_path: str, max_w: float, max_h: float):
    if not img_rel_path:
        return None
    full_path = os.path.normpath(img_rel_path)
    if not os.path.exists(full_path):
        if not full_path.startswith("static"):
            alt_path = os.path.join(config.STATIC_DIR, img_rel_path)
            if os.path.exists(alt_path):
                full_path = alt_path
            else:
                return None
        else:
            return None

    try:
        with PILImage.open(full_path) as pil_im:
            w, h = pil_im.size
            if w <= 0 or h <= 0:
                return None
            aspect = float(h) / float(w)
            calc_w = max_w
            calc_h = max_w * aspect
            if calc_h > max_h:
                calc_h = max_h
                calc_w = max_h / aspect
            return RLImage(full_path, width=calc_w, height=calc_h)
    except Exception:
        return None

def generate_audit_pdf(audit: dict) -> bytes:
    """
    Generates a professional, executive-grade PDF security audit certificate.
    Adheres strictly to the Karachi Gymkhana Club institutional visual identity
    with gold standard typography, high-contrast plates, and dual camera evidence.
    """
    entry = audit.get("entry") or {}
    exit_rec = audit.get("exit") or {}
    thumb = entry or exit_rec or {}

    is_unreg = bool(
        "Unknown" in (thumb.get("access_type") or "") or
        "No RFID" in (thumb.get("access_type") or "") or
        "Unregistered" in (thumb.get("name") or "") or
        thumb.get("mem_id") in ("GUEST-LOG", "AI-CAM", "UNREGISTERED", "")
    )
    is_member = not is_unreg and bool(thumb.get("mem_id"))

    ref_id = f"AUD-{str(thumb.get('id', 1)).zfill(6)}"
    duration = audit.get("duration") or "-- --"
    status_str = (audit.get("status") or "Inside Facility").upper()
    visit_date = str(thumb.get("timestamp", ""))[:10] or config.get_pkt_today()
    gen_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Document setup (A4: 595.27 x 841.89 pt, margins: 28pt)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=28,
        rightMargin=28,
        topMargin=28,
        bottomMargin=28
    )
    printable_w = 595.27 - 56  # 539.27 pt

    # Color Palette: Gold Standard Institutional
    c_gold = colors.HexColor("#D4AF37")
    c_dark_gold = colors.HexColor("#996515")
    c_navy = colors.HexColor("#0F172A")
    c_slate = colors.HexColor("#1E293B")
    c_light_slate = colors.HexColor("#334155")
    c_muted = colors.HexColor("#64748B")
    c_card_bg = colors.HexColor("#F8FAFC")
    c_border = colors.HexColor("#E2E8F0")
    c_emerald = colors.HexColor("#059669")
    c_amber = colors.HexColor("#D97706")
    c_rose = colors.HexColor("#E11D48")

    # Styles
    base_styles = getSampleStyleSheet()
    s_title = ParagraphStyle('DocTitle', parent=base_styles['Normal'], fontName='Helvetica-Bold', fontSize=18, leading=22, textColor=c_navy)
    s_subtitle = ParagraphStyle('DocSub', parent=base_styles['Normal'], fontName='Helvetica-Bold', fontSize=8, leading=11, textColor=c_dark_gold)
    s_sec_title = ParagraphStyle('SecTitle', parent=base_styles['Normal'], fontName='Helvetica-Bold', fontSize=11, leading=14, textColor=c_slate)
    s_bold_sm = ParagraphStyle('BoldSm', parent=base_styles['Normal'], fontName='Helvetica-Bold', fontSize=9, leading=12, textColor=c_slate)
    s_label = ParagraphStyle('LabelSm', parent=base_styles['Normal'], fontName='Helvetica-Bold', fontSize=7.5, leading=10, textColor=c_muted)
    s_value = ParagraphStyle('ValueSm', parent=base_styles['Normal'], fontName='Helvetica', fontSize=8.5, leading=11, textColor=c_slate)
    s_mono = ParagraphStyle('MonoSm', parent=base_styles['Normal'], fontName='Courier-Bold', fontSize=8.5, leading=11, textColor=c_slate)
    s_plate = ParagraphStyle('PlateText', parent=base_styles['Normal'], fontName='Courier-Bold', fontSize=16, leading=18, textColor=c_navy, alignment=TA_CENTER)
    s_badge = ParagraphStyle('BadgeText', parent=base_styles['Normal'], fontName='Helvetica-Bold', fontSize=8, leading=10, alignment=TA_CENTER)
    s_footer = ParagraphStyle('FootText', parent=base_styles['Normal'], fontName='Helvetica', fontSize=7, leading=9, textColor=c_muted, alignment=TA_CENTER)

    story = []

    # 1. Institutional Header
    logo_img = _safe_rl_image(config.LOGO_PATH, max_w=72, max_h=52)
    header_text = [
        Paragraph("KARACHI GYMKHANA CLUB", s_title),
        Paragraph("FOUNDED 1886 &bull; SECURITY &amp; ACCESS CONTROL DIVISION", s_subtitle),
        Spacer(1, 2),
        Paragraph("OFFICIAL VEHICLE AUDIT &amp; EVIDENCE CERTIFICATE", s_sec_title)
    ]
    if logo_img:
        hdr_table = Table([[logo_img, header_text]], colWidths=[80, printable_w - 80])
    else:
        hdr_table = Table([[header_text]], colWidths=[printable_w])

    hdr_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(hdr_table)
    story.append(Spacer(1, 6))

    # Gold Decorative Rule
    story.append(HRFlowable(width="100%", thickness=2.5, color=c_gold, spaceBefore=0, spaceAfter=8))

    # 2. Executive Telemetry Ribbon
    status_bg = c_emerald if "EXITED" in status_str else (c_amber if "ALERT" in status_str else c_slate)
    v_badge_color = c_emerald if is_member else (c_amber if "UNKNOWN" in (thumb.get("access_type") or "").upper() else c_rose)
    v_badge_text = "RFID VERIFIED MEMBER" if is_member else ("UNKNOWN RFID TAG" if is_unreg else "OPTICAL CAPTURE")

    ribbon_data = [
        [
            Paragraph("<b>REPORT REFERENCE</b><br/>" + ref_id, s_mono),
            Paragraph("<b>SECURITY VERDICT</b><br/>" + f'<font color="{v_badge_color.hexval()}"><b>{v_badge_text}</b></font>', s_bold_sm),
            Paragraph("<b>FACILITY STATUS</b><br/>" + f'<font color="{status_bg.hexval()}"><b>{status_str}</b></font>', s_bold_sm),
            Paragraph("<b>RECORD DATE</b><br/>" + visit_date, s_mono),
            Paragraph("<b>GENERATED (PKT)</b><br/>" + gen_time[11:19], s_mono),
        ]
    ]
    ribbon_table = Table(ribbon_data, colWidths=[105, 125, 105, 100, 104])
    ribbon_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), c_card_bg),
        ('BOX', (0, 0), (-1, -1), 1, c_border),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, c_border),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(ribbon_table)
    story.append(Spacer(1, 8))

    # 3. Two-Column Card Grid: Member Profile & Vehicle Details
    col_w = (printable_w - 10) / 2.0  # ~264.5 pt each

    # Card 1: Member / Driver Profile
    pfp_img = _safe_rl_image(thumb.get("Profile_pic") or thumb.get("profile_pic"), max_w=46, max_h=46)
    name_str = thumb.get("name") or "Unregistered Visitor"
    mem_id_str = thumb.get("mem_id") or "N/A"
    epc_str = thumb.get("scanned_tag") or "No Tag"
    if epc_str == "NO_TAG":
        epc_str = "No Tag Detected"

    member_info_flow = [
        Paragraph(f"<b>{name_str}</b>", ParagraphStyle('MName', parent=s_bold_sm, fontSize=11, leading=13)),
        Paragraph(f'<font color="#64748B">ID: </font><b>{mem_id_str}</b> &bull; ' + ('<font color="#059669"><b>Active Member</b></font>' if is_member else '<font color="#DC2626"><b>Unregistered</b></font>'), s_value),
        Paragraph(f'<font color="#64748B">RFID EPC: </font><font size="7">{epc_str}</font>', s_mono)
    ]
    if pfp_img:
        m_row = [[pfp_img, member_info_flow]]
        m_tbl = Table(m_row, colWidths=[52, col_w - 68])
    else:
        initial = (name_str[:1] or "?").upper()
        initial_block = Paragraph(f'<font size="16" color="#64748B"><b>[{initial}]</b></font>', s_badge)
        m_row = [[initial_block, member_info_flow]]
        m_tbl = Table(m_row, colWidths=[40, col_w - 56])

    m_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))

    card_member_content = [
        Paragraph("<b>DRIVER &bull; MEMBER PROFILE</b>", s_label),
        Spacer(1, 4),
        m_tbl,
        Spacer(1, 5),
        Table([
            [Paragraph("Membership Status", s_label), Paragraph("Active Club Member" if is_member else "Unregistered / Visitor", s_value)],
            [Paragraph("Access Protocol", s_label), Paragraph(thumb.get("access_type") or "UHF RFID Access", s_value)],
        ], colWidths=[90, col_w - 106], style=[
            ('LINEABOVE', (0, 0), (-1, 0), 0.5, c_border),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ])
    ]

    # Card 2: Vehicle & Transit Details
    plate_str = thumb.get("vehicle_number") or "NO PLATE"
    make_str = thumb.get("make_model") or "Vehicle Make Unspecified"
    gate_str = thumb.get("gate_no") or "Gate-01"
    entry_ts = str(entry.get("timestamp", "")) if entry else "--"
    exit_ts = str(exit_rec.get("timestamp", "")) if exit_rec else "--"

    plate_box = Table([[Paragraph(plate_str, s_plate)]], colWidths=[col_w - 24])
    plate_box.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#EEF2F6")),
        ('BOX', (0, 0), (-1, -1), 1.5, colors.HexColor("#94A3B8")),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))

    card_vehicle_content = [
        Paragraph("<b>VEHICLE &bull; PASSAGE PARTICULARS</b>", s_label),
        Spacer(1, 3),
        plate_box,
        Spacer(1, 4),
        Table([
            [Paragraph("Make &amp; Model", s_label), Paragraph(make_str, s_bold_sm)],
            [Paragraph("Gate Lane", s_label), Paragraph(gate_str, s_value)],
            [Paragraph("Duration of Stay", s_label), Paragraph(f'<font color="#4F46E5"><b>{duration}</b></font>', s_bold_sm)],
            [Paragraph("Entry Timestamp", s_label), Paragraph(entry_ts[11:19] if len(entry_ts) >= 19 else entry_ts, s_mono)],
            [Paragraph("Exit Timestamp", s_label), Paragraph(exit_ts[11:19] if len(exit_ts) >= 19 else exit_ts, s_mono)],
        ], colWidths=[85, col_w - 101], style=[
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ])
    ]

    card_tbl = Table([[card_member_content, card_vehicle_content]], colWidths=[col_w, col_w])
    card_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), c_card_bg),
        ('BACKGROUND', (1, 0), (1, 0), c_card_bg),
        ('BOX', (0, 0), (0, 0), 1, c_border),
        ('BOX', (1, 0), (1, 0), 1, c_border),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING', (0, 0), (-1, -1), 9),
        ('RIGHTPADDING', (0, 0), (-1, -1), 9),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(card_tbl)
    story.append(Spacer(1, 8))

    # 4. Synchronized Optical Proof & Camera Evidence
    story.append(Paragraph("<b>SYNCHRONIZED OPTICAL PROOF &bull; CAMERA EVIDENCE JOURNAL</b>", s_label))
    story.append(Spacer(1, 3))

    evidence_panels = []

    # Check for Entry Evidence
    entry_hik = entry.get("image_path")
    entry_dahua = entry.get("plate_image_path")
    if entry_hik or entry_dahua:
        im_hik = _safe_rl_image(entry_hik, max_w=col_w - 20, max_h=120)
        im_dahua = _safe_rl_image(entry_dahua, max_w=col_w - 20, max_h=120)
        
        cell_hik = [
            Paragraph("<b>HIKVISION FULL VEHICLE OVERVIEW (WIDE ANGLE)</b>", s_label),
            Spacer(1, 2),
            im_hik or Paragraph('<font color="#94A3B8">[No Overview Image Captured]</font>', s_label)
        ]
        cell_dahua = [
            Paragraph("<b>DAHUA GATE SHOT (LICENSE PLATE CLOSE-UP)</b>", s_label),
            Spacer(1, 2),
            im_dahua or Paragraph('<font color="#94A3B8">[No Dahua Close-up Captured]</font>', s_label)
        ]
        evidence_panels.append([cell_hik, cell_dahua])

    # Check for Exit Evidence
    exit_hik = exit_rec.get("image_path")
    exit_dahua = exit_rec.get("plate_image_path")
    if (exit_hik or exit_dahua) and (exit_hik != entry_hik or exit_dahua != entry_dahua):
        im_x_hik = _safe_rl_image(exit_hik, max_w=col_w - 20, max_h=120)
        im_x_dahua = _safe_rl_image(exit_dahua, max_w=col_w - 20, max_h=120)
        cell_x_hik = [
            Paragraph("<b>EXIT HIKVISION OVERVIEW SHOT</b>", s_label),
            Spacer(1, 2),
            im_x_hik or Paragraph('<font color="#94A3B8">[No Exit Overview Image]</font>', s_label)
        ]
        cell_x_dahua = [
            Paragraph("<b>EXIT DAHUA PLATE CLOSE-UP</b>", s_label),
            Spacer(1, 2),
            im_x_dahua or Paragraph('<font color="#94A3B8">[No Exit Plate Close-up]</font>', s_label)
        ]
        evidence_panels.append([cell_x_hik, cell_x_dahua])

    if not evidence_panels:
        # Placeholder panel if no photos on file
        empty_box = Table([[
            Paragraph('<font color="#64748B"><b>No optical evidence images were attached to this transit record.</b><br/>RFID antenna detection was verified directly without optical line-crossing capture.</font>', s_label)
        ]], colWidths=[printable_w])
        empty_box.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), c_card_bg),
            ('BOX', (0, 0), (-1, -1), 1, c_border),
            ('TOPPADDING', (0, 0), (-1, -1), 14),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 14),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ]))
        story.append(empty_box)
    else:
        for panel_rows in evidence_panels:
            ev_table = Table([panel_rows], colWidths=[col_w, col_w])
            ev_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), c_card_bg),
                ('BOX', (0, 0), (-1, -1), 1, c_border),
                ('INNERGRID', (0, 0), (-1, -1), 0.5, c_border),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]))
            story.append(ev_table)
            story.append(Spacer(1, 6))

    # 5. Chain of Custody & Authentication Footer
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=1, color=c_gold, spaceBefore=0, spaceAfter=5))

    footer_data = [
        [
            Paragraph("<b>OFFICIAL SECURITY REGISTRY RECORD</b><br/>Karachi Gymkhana Club &bull; VAMS Core v3.0", s_label),
            Paragraph("<b>CRYPTOGRAPHIC HASH</b><br/>" + f"SHA256-{ref_id}-{visit_date.replace('-', '')}", s_mono),
            Paragraph("<b>AUTHENTICATED BY</b><br/>Automated Gate Sentry &bull; Lane 1", s_label),
        ]
    ]
    foot_table = Table(footer_data, colWidths=[185, 180, 174])
    foot_table.setStyle(TableStyle([
        ('TOPPADDING', (0, 0), (-1, -1), 1),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(foot_table)
    story.append(Spacer(1, 4))
    story.append(Paragraph("This document is an official electronically generated security audit certificate under the authority of Karachi Gymkhana Club. Any unauthorized alteration or reproduction is strictly prohibited.", s_footer))

    doc.build(story)
    return buf.getvalue()
