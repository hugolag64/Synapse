from datetime import datetime, timedelta

def format_ics_date(dt: datetime) -> str:
    """Format datetime to ICS format YYYYMMDDTHHMMSS"""
    return dt.strftime("%Y%m%dT%H%M%S")

def generate_ics_content(events: list) -> bytes:
    """
    Generate ICS file content for a list of events.
    Each event in list should be a dict: {'title': str, 'start': datetime, 'duration_hours': int}
    """
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Synapse//Medecine//FR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]

    for event in events:
        start = event['start']
        end = start + timedelta(hours=event.get('duration_hours', 1))
        dtstamp = datetime.now()

        lines.extend([
            "BEGIN:VEVENT",
            f"SUMMARY:{event['title']}",
            f"DTSTART:{format_ics_date(start)}",
            f"DTEND:{format_ics_date(end)}",
            f"DTSTAMP:{format_ics_date(dtstamp)}",
            f"UID:{event['title'].replace(' ', '_')}_{format_ics_date(start)}@synapse",
            "DESCRIPTION:Rappel généré par Synapse",
            "STATUS:CONFIRMED",
            "END:VEVENT",
        ])

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines).encode('utf-8')
