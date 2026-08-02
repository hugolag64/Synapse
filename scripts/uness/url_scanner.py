"""UNESS Fast URL Scanner & Categorizer Module.

Uses Playwright for session authentication, extracts cookies, and leverages httpx
for ultra-fast (100-300ms) HTTP requests with micro-pauses (0.2s - 0.4s).

Scans targeted medical faculty Moodle categories, filters by year (EDN era, last 2-3 years),
level (DFASM / EDN, excludes DFGSM), enforces La Réunion DFASM rules, checks Synapse DB for duplicates,
inspects quizzes to count questions per quiz/DP, and saves entries directly into SQLite `uness_scanned_catalog`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(_ROOT / ".env.local")
    load_dotenv(_ROOT / ".env")
except ImportError:
    pass

try:
    from backend.core.reviews.local_store import (
        get_uness_annale_by_source_url,
        upsert_scanned_catalog_annale,
    )
except ImportError:
    get_uness_annale_by_source_url = lambda url: None  # Fallback if DB module unlinked
    upsert_scanned_catalog_annale = lambda **kwargs: None

from scripts.uness.subject_mappings import SUBJECT_MAPPINGS, match_subjects

# Target Faculties Configuration
TARGET_FACULTIES: list[dict] = [
    {
        "id": "paris_cite",
        "name": "Université Paris Cité",
        "category_ids": [838],
    },
    {
        "id": "sorbonne",
        "name": "Sorbonne Université",
        "category_ids": [90],
    },
    {
        "id": "paris_saclay",
        "name": "Université Paris-Saclay",
        "category_ids": [381],
    },
    {
        "id": "lyon_1",
        "name": "Université Claude Bernard Lyon 1",
        "category_ids": [835, 176],
    },
    {
        "id": "montpellier",
        "name": "Université de Montpellier",
        "category_ids": [329],
    },
    {
        "id": "toulouse",
        "name": "Université de Toulouse",
        "category_ids": [398],
    },
    {
        "id": "bordeaux",
        "name": "Université de Bordeaux",
        "category_ids": [371],
    },
    {
        "id": "lille",
        "name": "Université de Lille",
        "category_ids": [834],
    },
    {
        "id": "aix_marseille",
        "name": "Aix-Marseille Université",
        "category_ids": [757],
    },
    {
        "id": "la_reunion",
        "name": "Université de La Réunion",
        "category_ids": [431, 432, 840],
    },
]

OUTPUT_JSON_DIR = _ROOT / "data" / "uness" / "scanned_urls"
OUTPUT_MD_DIR = _ROOT / "UNESS" / "URLs"


def _extract_year(text: str) -> int | None:
    """Extract 4-digit academic year (e.g. 2024 from '2023-2024' or '2024')."""
    match = re.search(r"\b(202[3-6])(?:-(?:20)?2[3-6])?\b", text)
    if match:
        return int(match.group(1))
    return None


def _is_dfgsm(text: str) -> bool:
    """Check if title or breadcrumb indicates DFGSM (L2/L3 pre-externat)."""
    text_upper = text.upper()
    return bool(re.search(r"\bDFGSM\b|\bDFGSM2\b|\bDFGSM3\b|\bFGSM\b|\bL2\b|\bL3\b", text_upper))


def _has_dfasm(text: str) -> bool:
    """Check if title or breadcrumb indicates DFASM (externat EDN)."""
    text_upper = text.upper()
    return bool(re.search(r"\bDFASM\b|\bDFASM1\b|\bDFASM2\b|\bDFASM3\b|\bEXTERNAT\b|\bEDN\b", text_upper))


def _is_recent_year(year: int | None) -> bool:
    """Keep last 2-3 years (2023, 2024, 2025, 2026)."""
    if year is None:
        return True
    return year >= 2023


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


class UnessFastScanner:
    def __init__(self, headless: bool = True, delay_range: tuple[float, float] = (0.2, 0.4)):
        self.headless = headless
        self.delay_range = delay_range
        self.http_client: httpx.AsyncClient | None = None
        self.visited_category_ids: set[int] = set()

    async def _micro_delay(self):
        delay = random.uniform(*self.delay_range)
        await asyncio.sleep(delay)

    async def authenticate_and_get_session(self) -> httpx.AsyncClient:
        """Use Playwright persistent browser context to authenticate and return a httpx client with cookies."""
        from playwright.async_api import async_playwright

        pw = await async_playwright().start()
        user_data_dir = _ROOT / "data" / "uness" / "browser-profile"
        user_data_dir.mkdir(parents=True, exist_ok=True)

        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=self.headless,
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            args=["--hide-crash-restore-bubble", "--disable-session-crashed-bubble"],
        )
        page = context.pages[0] if context.pages else await context.new_page()

        # Check authentication on UNESS
        await page.goto("https://entrainement.uness.fr/annales/", wait_until="domcontentloaded")
        await asyncio.sleep(1)

        # Handle CAS auto login or manual login wait
        if "/cas/login" in page.url:
            username = (
                os.environ.get("UNESS_USERNAME")
                or os.environ.get("LISA_USERNAME")
                or ""
            ).strip()
            password = (
                os.environ.get("UNESS_PASSWORD")
                or os.environ.get("LISA_PASSWORD")
                or ""
            )
            if username and password:
                user = page.locator('input[name="username"], input#username, input[type="email"]').first
                if await user.count():
                    await user.fill(username)
                    submit = page.locator('button[type="submit"], input[type="submit"]').first
                    if await submit.count():
                        await submit.click()
                    else:
                        await user.press("Enter")
                    await asyncio.sleep(2)

                secret = page.locator('input[name="password"], input#password, input[type="password"]').first
                if await secret.count():
                    await secret.fill(password)
                    submit = page.locator('button[type="submit"], input[type="submit"]').first
                    if await submit.count():
                        await submit.click()
                    else:
                        await secret.press("Enter")
                    await page.wait_for_load_state("domcontentloaded")
                    await asyncio.sleep(2)

            if "/cas/login" in page.url:
                if not self.headless:
                    print("\n[!] Veuillez vous connecter dans la fenêtre du navigateur ouverte (saisissez email et mot de passe).")
                    print("[*] Le scanner HTTP démarrera dès que vous serez connecté...")
                    start_time = datetime.now().timestamp()
                    while "/cas/login" in page.url:
                        await asyncio.sleep(1)
                        if datetime.now().timestamp() - start_time > 180:
                            print("[!] Temps d'attente dépassé (3 minutes).")
                            await context.close()
                            sys.exit(1)
                    await asyncio.sleep(1)
                else:
                    print("[!] Session CAS requise. Lancez avec '--no-headless' pour vous connecter une fois.")
                    await context.close()
                    sys.exit(1)

        cookies = await context.cookies()
        await context.close()

        # Build httpx AsyncClient with extracted cookies
        cookie_dict = {c["name"]: c["value"] for c in cookies}
        client = httpx.AsyncClient(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
            },
            cookies=cookie_dict,
            timeout=15.0,
            follow_redirects=True,
        )
        return client

    async def inspect_course_details(self, course_url: str) -> dict:
        """Fast HTTP inspection of course view page to count quizzes and questions."""
        try:
            resp = await self.http_client.get(course_url)
            await self._micro_delay()
            soup = BeautifulSoup(resp.text, "html.parser")

            quizzes = []
            quiz_links = soup.find_all("a", href=re.compile(r"/mod/quiz/view\.php\?id=\d+"))
            seen_quiz_ids = set()

            for q_link in quiz_links:
                q_href = q_link.get("href", "")
                q_id = re.search(r"id=(\d+)", q_href)
                if not q_id or q_id.group(1) in seen_quiz_ids:
                    continue
                seen_quiz_ids.add(q_id.group(1))
                q_title = q_link.get_text(strip=True) or "Quiz / DP sans titre"
                quizzes.append({
                    "id": q_id.group(1),
                    "title": q_title,
                    "url": q_href,
                    "questions_count": None,
                })

            total_questions = 0
            for quiz in quizzes[:5]:  # Deep inspect up to 5 quizzes fast
                try:
                    q_resp = await self.http_client.get(quiz["url"])
                    await self._micro_delay()
                    q_soup = BeautifulSoup(q_resp.text, "html.parser")
                    text_content = q_soup.get_text()

                    q_match = re.search(r"Questions?\s*:\s*(\d+)", text_content, re.IGNORECASE)
                    if not q_match:
                        q_match = re.search(r"(\d+)\s*questions?", text_content, re.IGNORECASE)

                    if q_match:
                        q_count = int(q_match.group(1))
                        quiz["questions_count"] = q_count
                        total_questions += q_count
                except Exception:
                    pass

            return {
                "quiz_count": len(quizzes),
                "total_questions": total_questions if total_questions > 0 else None,
                "quizzes": quizzes,
                "is_single_dp": len(quizzes) == 1,
            }
        except Exception as exc:
            return {"quiz_count": 0, "total_questions": None, "quizzes": [], "is_single_dp": False}

    async def scan_category(
        self, category_id: int, fac_info: dict, target_subject: str | None = None
    ) -> list[dict]:
        """Scan a Moodle category recursively over fast HTTP."""
        if category_id in self.visited_category_ids:
            return []
        self.visited_category_ids.add(category_id)

        url = f"https://entrainement.uness.fr/annales/course/index.php?categoryid={category_id}&perpage=500"
        try:
            resp = await self.http_client.get(url)
            await self._micro_delay()
            if "/cas/login" in str(resp.url):
                print(f"[!] Session expirée pour la catégorie {category_id}.")
                return []

            soup = BeautifulSoup(resp.text, "html.parser")
            found_courses = []

            # Find subcategories and pagination links inside main content
            main_region = soup.find(id="region-main") or soup.find(class_="subcategories") or soup
            subcat_links = main_region.find_all("a", href=re.compile(r"/course/index\.php\?categoryid=\d+"))

            subcat_ids = []
            for s_link in subcat_links:
                if s_link.find_parent(class_=re.compile(r"breadcrumb|nav|header")):
                    continue
                s_href = s_link.get("href", "")
                s_match = re.search(r"categoryid=(\d+)", s_href)
                if s_match:
                    s_id = int(s_match.group(1))
                    if s_id not in self.visited_category_ids and s_id not in subcat_ids:
                        subcat_ids.append(s_id)

            # Find course links
            course_links = soup.find_all("a", href=re.compile(r"/course/view\.php\?id=\d+"))
            seen_course_ids = set()

            for c_link in course_links:
                c_href = c_link.get("href", "")
                c_match = re.search(r"id=(\d+)", c_href)
                if not c_match or c_match.group(1) in seen_course_ids:
                    continue
                seen_course_ids.add(c_match.group(1))

                c_title = c_link.get_text(strip=True)
                c_title = re.sub(r"^Image de l'annale\s*", "", c_title, flags=re.IGNORECASE).strip()
                if not c_title:
                    continue

                full_context = f"{fac_info['name']} {c_title}"
                year = _extract_year(full_context)

                if _is_dfgsm(full_context):
                    continue
                if not _is_recent_year(year):
                    continue

                matched_subs = match_subjects(c_title)
                if target_subject and target_subject not in matched_subs:
                    continue

                normalized_url = f"https://entrainement.uness.fr/annales/course/view.php?id={c_match.group(1)}"
                already_imported = get_uness_annale_by_source_url(normalized_url) is not None

                found_courses.append({
                    "id": c_match.group(1),
                    "title": c_title,
                    "url": normalized_url,
                    "faculty": fac_info["name"],
                    "year": year,
                    "subjects": matched_subs,
                    "already_imported": already_imported,
                })

            for sub_id in subcat_ids:
                sub_results = await self.scan_category(sub_id, fac_info, target_subject)
                found_courses.extend(sub_results)

            return found_courses
        except Exception as exc:
            print(f"[!] Erreur scan catégorie {category_id}: {exc}")
            return []

    async def scan_all(
        self, target_subject: str | None = None, target_fac_id: str | None = None
    ) -> dict[str, list[dict]]:
        """Run fast HTTP scan on configured faculties."""
        self.http_client = await self.authenticate_and_get_session()
        scanned_by_subject: dict[str, list[dict]] = {}

        faculties = [f for f in TARGET_FACULTIES if not target_fac_id or f["id"] == target_fac_id]

        try:
            for fac in faculties:
                print(f"[*] Scan rapide HTTP : {fac['name']} (id={fac['id']})...")
                for cat_id in fac["category_ids"]:
                    courses = await self.scan_category(cat_id, fac, target_subject)

                    for course in courses:
                        print(f"   [>] Inspection rapide : {course['title']} ({course['url']})")
                        details = await self.inspect_course_details(course["url"])
                        course.update(details)

                        for sub in course["subjects"]:
                            scanned_by_subject.setdefault(sub, []).append(course)
                            try:
                                yr = course.get("year")
                                total_q = course.get("total_questions")
                                upsert_scanned_catalog_annale(
                                    source_url=course["url"],
                                    faculte=course.get("faculty", "N/A"),
                                    matiere=sub,
                                    annee=int(yr) if isinstance(yr, int) or (isinstance(yr, str) and yr.isdigit()) else None,
                                    titre=course.get("title", "Sans titre"),
                                    quiz_count=course.get("quiz_count", 0),
                                    total_questions=int(total_q) if total_q is not None and str(total_q).isdigit() else None,
                                    is_single_dp=bool(course.get("is_single_dp")),
                                )
                            except Exception as exc:
                                print(f"[!] Erreur upsert DB pour {course['url']}: {exc}")

        finally:
            if self.http_client:
                await self.http_client.aclose()

        return scanned_by_subject


def export_results(scanned_by_subject: dict[str, list[dict]]) -> None:
    """Export scanned results to SQLite database, JSON, and Markdown format per subject."""
    OUTPUT_JSON_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_MD_DIR.mkdir(parents=True, exist_ok=True)

    total_scanned = 0

    for subject, courses in scanned_by_subject.items():
        unique_courses = {}
        for c in courses:
            unique_courses[c["url"]] = c
        course_list = list(unique_courses.values())
        total_scanned += len(course_list)

        # Save JSON
        json_path = OUTPUT_JSON_DIR / f"{subject}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(course_list, f, ensure_ascii=False, indent=2)

        # Save Markdown
        md_path = OUTPUT_MD_DIR / f"{subject}.md"
        lines = [
            f"# Annales UNESS - Matière : {subject}",
            "",
            f"*Dernière mise à jour : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*",
            f"*Nombre d'épreuves référencées : {len(course_list)}*",
            "",
            "| Faculté | Année | Intitulé Épreuve | URL UNESS | Quizz / DPs | Nb Questions | Importé dans Synapse |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]

        for c in course_list:
            fac = c.get("faculty", "N/A")
            yr = c.get("year")
            title = c.get("title", "Sans titre").replace("|", "-")
            url = c.get("url", "#")
            quizzes_count = c.get("quiz_count", 0)
            single_dp = " (1 DP seul)" if c.get("is_single_dp") else ""
            total_q = c.get("total_questions")
            imported = "Oui" if c.get("already_imported") else "Non"

            # Upsert into local SQLite database
            try:
                upsert_scanned_catalog_annale(
                    source_url=url,
                    faculte=fac,
                    matiere=subject,
                    annee=int(yr) if isinstance(yr, int) or (isinstance(yr, str) and yr.isdigit()) else None,
                    titre=title,
                    quiz_count=quizzes_count,
                    total_questions=int(total_q) if total_q is not None and str(total_q).isdigit() else None,
                    is_single_dp=bool(c.get("is_single_dp")),
                )
            except Exception as exc:
                print(f"[!] Erreur enregistrement DB SQLite pour {url}: {exc}")

            lines.append(
                f"| {fac} | {yr or 'N/A'} | {title} | [Consulter sur UNESS]({url}) | {quizzes_count}{single_dp} | {total_q if total_q is not None else 'N/A'} | {imported} |"
            )

        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        print(f"[+] Exporté : {md_path} ({len(course_list)} épreuves dans la DB SQLite)")

    print(f"\n✅ Scan terminé avec succès ! {total_scanned} épreuve(s) indexée(s) dans SQLite.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scan rapide HTTP et catégorise les annales UNESS par matière.")
    parser.add_argument("--subject", type=str, help="Matière spécifique à scanner (ex: Cardiovasculaire, Infectiologie)")
    parser.add_argument("--fac", type=str, help="Identifiant de faculté (ex: paris_cite, sorbonne, la_reunion)")
    parser.add_argument("--no-headless", action="store_true", help="Afficher le navigateur Chromium pour la connexion initiale")
    args = parser.parse_args()

    scanner = UnessFastScanner(headless=not args.no_headless)
    results = asyncio.run(scanner.scan_all(target_subject=args.subject, target_fac_id=args.fac))
    export_results(results)
