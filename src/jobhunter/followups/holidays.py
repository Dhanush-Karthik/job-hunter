"""IST public holidays 2026-2027: national gazetted holidays plus Tamil Nadu / Karnataka bank holidays.

Best effort from published calendars; lunar-calendar festivals can move by a day, so the owner adds corrections
through settings.followups.extra_holidays. Only weekday dates matter to business-day maths, but weekend dates are
kept so the list reads like the published calendars.
"""

from __future__ import annotations

HOLIDAYS: dict[str, str] = {
    # 2026
    "2026-01-01": "New Year's Day",
    "2026-01-15": "Pongal / Makar Sankranti",
    "2026-01-16": "Thiruvalluvar Day",
    "2026-01-17": "Uzhavar Thirunal",
    "2026-01-26": "Republic Day",
    "2026-03-04": "Holi",
    "2026-03-19": "Ugadi / Telugu New Year",
    "2026-03-21": "Eid-ul-Fitr",
    "2026-03-26": "Ram Navami",
    "2026-03-31": "Mahavir Jayanti",
    "2026-04-03": "Good Friday",
    "2026-04-14": "Tamil New Year / Ambedkar Jayanti",
    "2026-05-01": "May Day / Buddha Purnima",
    "2026-05-27": "Bakrid (Eid-ul-Adha)",
    "2026-06-26": "Muharram",
    "2026-08-15": "Independence Day",
    "2026-08-26": "Milad-un-Nabi",
    "2026-09-04": "Janmashtami",
    "2026-09-14": "Ganesh Chaturthi",
    "2026-10-02": "Gandhi Jayanti",
    "2026-10-19": "Ayudha Puja / Maha Navami",
    "2026-10-20": "Vijayadashami (Dussehra)",
    "2026-11-01": "Karnataka Rajyotsava",
    "2026-11-08": "Deepavali",
    "2026-11-24": "Guru Nanak Jayanti",
    "2026-12-25": "Christmas",
    # 2027
    "2027-01-01": "New Year's Day",
    "2027-01-15": "Pongal / Makar Sankranti",
    "2027-01-16": "Thiruvalluvar Day",
    "2027-01-17": "Uzhavar Thirunal",
    "2027-01-26": "Republic Day",
    "2027-03-10": "Eid-ul-Fitr",
    "2027-03-22": "Holi",
    "2027-03-26": "Good Friday",
    "2027-04-07": "Ugadi / Telugu New Year",
    "2027-04-14": "Tamil New Year / Ambedkar Jayanti",
    "2027-04-15": "Ram Navami",
    "2027-04-18": "Mahavir Jayanti",
    "2027-05-01": "May Day",
    "2027-05-17": "Bakrid (Eid-ul-Adha)",
    "2027-05-20": "Buddha Purnima",
    "2027-06-15": "Muharram",
    "2027-08-15": "Independence Day",
    "2027-08-25": "Janmashtami",
    "2027-09-04": "Ganesh Chaturthi",
    "2027-10-02": "Gandhi Jayanti",
    "2027-10-08": "Ayudha Puja / Maha Navami",
    "2027-10-09": "Vijayadashami (Dussehra)",
    "2027-10-29": "Deepavali",
    "2027-11-01": "Karnataka Rajyotsava",
    "2027-11-15": "Guru Nanak Jayanti",
    "2027-12-25": "Christmas",
}
