"""
Utilitaires partagés entre les pages frontend.
"""
import datetime
from nicegui import ui
from loguru import logger
from backend.state.store import data_store
from backend.core.notion.service import notion_service
from backend.config.settings import NOTION_PROPS as P
from backend.core.notion.payloads import checkbox, notion_date, url_prop


async def update_course_action(c, properties: dict, refresh_fn=None, client=None):
    """
    Mise à jour optimiste d'un cours (locale + Notion en arrière-plan).

    - Applique immédiatement les changements sur l'objet local (et son jumeau dans le store).
    - Appelle Notion en async.
    - En cas d'échec : rollback des valeurs locales + notification.
    - refresh_fn (callable) : re-render à appeler après mise à jour locale.
    - client : contexte NiceGUI pour notifier depuis un task background.

    Les clés de `properties` doivent utiliser NOTION_PROPS.X (jamais de chaîne en dur).
    """
    if not client:
        try:
            client = ui.context.client
        except Exception:
            pass

    snapshot = {}

    try:
        async with data_store._cours_lock:
            real_c = next((x for x in data_store.cours if x.id == c.id), c)
        targets = [c] if real_c is c else [c, real_c]

        for target in targets:
            # ── Collège ────────────────────────────────────────────────────
            if P.URL_PDF_COLLEGE in properties:
                snapshot.setdefault(target, {})['url_pdf'] = target.url_pdf
                val = properties[P.URL_PDF_COLLEGE]
                target.url_pdf = val['url'] if isinstance(val, dict) else val

            if P.RAPPEL_COLLEGE in properties:
                snapshot.setdefault(target, {})['rappel_done'] = target.rappel_done
                val = properties[P.RAPPEL_COLLEGE]
                target.rappel_done = val['checkbox'] if isinstance(val, dict) and 'checkbox' in val else bool(val)

            if P.DATE_LECTURE_COLLEGE in properties:
                snapshot.setdefault(target, {})['date_1ere_lecture'] = target.date_1ere_lecture
                raw = properties[P.DATE_LECTURE_COLLEGE]
                date_str = raw.get('date', {}).get('start') if isinstance(raw, dict) else raw
                if date_str:
                    try:
                        target.date_1ere_lecture = datetime.date.fromisoformat(date_str)
                    except Exception:
                        pass

            if P.NB_LECTURES_COLLEGE in properties:
                snapshot.setdefault(target, {})['nb_lectures'] = target.nb_lectures
                val = properties[P.NB_LECTURES_COLLEGE]
                target.nb_lectures = val['number'] if isinstance(val, dict) and 'number' in val else int(val)

            # ── UE / Semestre ──────────────────────────────────────────────
            if P.URL_PDF_UE in properties:
                snapshot.setdefault(target, {})['url_pdf_ue'] = target.url_pdf_ue
                val = properties[P.URL_PDF_UE]
                target.url_pdf_ue = val['url'] if isinstance(val, dict) else val

            if P.RAPPEL_UE in properties:
                snapshot.setdefault(target, {})['rappel_ue_done'] = target.rappel_ue_done
                val = properties[P.RAPPEL_UE]
                target.rappel_ue_done = val['checkbox'] if isinstance(val, dict) and 'checkbox' in val else bool(val)

            if P.DATE_LECTURE_UE in properties:
                snapshot.setdefault(target, {})['date_1ere_lecture_ue'] = target.date_1ere_lecture_ue
                raw = properties[P.DATE_LECTURE_UE]
                date_str = raw.get('date', {}).get('start') if isinstance(raw, dict) else raw
                if date_str:
                    try:
                        target.date_1ere_lecture_ue = datetime.date.fromisoformat(date_str)
                    except Exception:
                        pass

            if P.NB_LECTURES_UE in properties:
                snapshot.setdefault(target, {})['nb_lectures_ue'] = target.nb_lectures_ue
                val = properties[P.NB_LECTURES_UE]
                target.nb_lectures_ue = val['number'] if isinstance(val, dict) and 'number' in val else int(val)

            # ── Checkboxes Collège ─────────────────────────────────────────
            for prop_key, attr_name in [
                (P.ANKI_COLLEGE,   'anki'),
                (P.QCM_COLLEGE,    'qcm_done'),
                (P.RESUME_COLLEGE, 'resume_done'),
                (P.CHATGPT_COLLEGE,'chatgpt_done'),
            ]:
                if prop_key in properties:
                    snapshot.setdefault(target, {})[attr_name] = getattr(target, attr_name, False)
                    val = properties[prop_key]
                    setattr(target, attr_name,
                            val['checkbox'] if isinstance(val, dict) and 'checkbox' in val else bool(val))

            # ── Checkboxes UE ──────────────────────────────────────────────
            for prop_key, attr_name in [
                (P.ANKI_UE,    'anki'),
                (P.QCM_FAIT,   'qcm_done'),
                (P.RESUME_UE,  'resume_done'),
                (P.CHATGPT_UE, 'chatgpt_done'),
            ]:
                if prop_key in properties:
                    snapshot.setdefault(target, {})[attr_name] = getattr(target, attr_name, False)
                    val = properties[prop_key]
                    setattr(target, attr_name,
                            val['checkbox'] if isinstance(val, dict) and 'checkbox' in val else bool(val))

            # ── Dates J3/J7/J14/J30 (college + UE) ────────────────────────
            for prop_key, attr_name in [
                (P.LECTURE_J3_COLLEGE,  "lecture_j3_college"),
                (P.LECTURE_J7_COLLEGE,  "lecture_j7_college"),
                (P.LECTURE_J14_COLLEGE, "lecture_j14_college"),
                (P.LECTURE_J30_COLLEGE, "lecture_j30_college"),
                (P.LECTURE_J3_UE,       "lecture_j3_ue"),
                (P.LECTURE_J7_UE,       "lecture_j7_ue"),
                (P.LECTURE_J14_UE,      "lecture_j14_ue"),
                (P.LECTURE_J30_UE,      "lecture_j30_ue"),
            ]:
                if prop_key in properties:
                    snapshot.setdefault(target, {})[attr_name] = getattr(target, attr_name, None)
                    raw = properties[prop_key]
                    date_str = raw.get('date', {}).get('start') if isinstance(raw, dict) else raw
                    if date_str:
                        try:
                            setattr(target, attr_name, datetime.date.fromisoformat(date_str))
                        except Exception:
                            pass

        if client:
            with client:
                if refresh_fn:
                    refresh_fn()
                ui.notify("Sauvegarde en cours...", type='ongoing', timeout=1.0)
        else:
            if refresh_fn:
                refresh_fn()

    except Exception as e:
        logger.error(f"[utils] Erreur mise à jour optimiste : {e}")
        return False

    # Sync Notion
    success = await notion_service.update_course(c.id, properties)

    if success:
        data_store.save_to_disk()
        # Invalider le cache des ReviewTask (les chips/dates ont peut-être changé)
        from backend.core.reviews.service import review_service
        review_service.invalidate_cache()
        if client:
            with client:
                ui.notify("Sauvegardé !", type='positive')
        return True
    else:
        # Rollback
        for target, old_vals in snapshot.items():
            for attr, old_val in old_vals.items():
                setattr(target, attr, old_val)
        if client:
            with client:
                if refresh_fn:
                    refresh_fn()
                ui.notify("Erreur Notion — modifications annulées", type='negative')
        return False
