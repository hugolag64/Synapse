"""Import local de banques DP/KFP préparées hors de Synapse."""

from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any


class ImportValidationError(ValueError):
    """Fichier d'import incompatible avec le contrat Synapse."""


@dataclass(frozen=True)
class ImportedQuestion:
    prompt: str
    answer: str
    explanation: str
    choices: tuple[str, ...] = ()


@dataclass(frozen=True)
class ImportedCase:
    fingerprint: str
    external_id: str
    kind: str
    title: str
    stem: str
    item_numbers: tuple[str, ...]
    questions: tuple[ImportedQuestion, ...]
    status: str
    review_reason: str = ""


@dataclass(frozen=True)
class ImportBatch:
    source: str
    cases: tuple[ImportedCase, ...]
    raw_text: str = ""


def _text(value: Any, field: str, *, required: bool = True) -> str:
    result = str(value or "").strip()
    if required and not result:
        raise ImportValidationError(f"Champ obligatoire absent : {field}")
    return result


def _item_numbers(raw: Any, title: str, stem: str) -> tuple[str, ...]:
    values = raw if isinstance(raw, list) else ([raw] if raw else [])
    found = {str(value).strip() for value in values if str(value).strip().isdigit()}
    if not found:
        found.update(re.findall(r"\bitem\s*(\d{1,3})\b", f"{title} {stem}", re.I))
    return tuple(sorted(found, key=lambda value: int(value)))


def _case_status(item_numbers: tuple[str, ...]) -> tuple[str, str]:
    if not item_numbers:
        return "needs_review", "ITEM introuvable dans le cas"
    if len(item_numbers) > 1:
        return "needs_review", "Plusieurs ITEM proposés : confirmation nécessaire"
    return "ready", ""


def parse_practice_bank(payload: Any) -> ImportBatch:
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8")
    
    # Si le texte brut contient plusieurs blocs JSON distincts collés ou à la suite { ... } \n { ... }
    if isinstance(payload, str):
        payload_str = payload.strip()
        try:
            payload = json.loads(payload_str)
        except json.JSONDecodeError:
            # Recherche de tous les objets JSON valides dans le texte avec un parser incrémental
            decoder = json.JSONDecoder()
            idx = 0
            found_objects = []
            while idx < len(payload_str):
                payload_str = payload_str[idx:].lstrip()
                if not payload_str:
                    break
                try:
                    obj, end_idx = decoder.raw_decode(payload_str)
                    found_objects.append(obj)
                    idx = end_idx
                except json.JSONDecodeError:
                    break
            
            if len(found_objects) > 1:
                all_cases = []
                for sub_obj in found_objects:
                    try:
                        sub_batch = parse_practice_bank(sub_obj)
                        all_cases.extend(sub_batch.cases)
                    except Exception:
                        continue
                if all_cases:
                    return ImportBatch(source="Import Multi-DP IA", cases=tuple(all_cases))
            
            raise ImportValidationError("Le fichier d'import n'est pas un JSON valide")
    # Cas où le payload contient plusieurs objets JSON collés bout à bout {obj1}{obj2}
    if isinstance(payload, str) and payload.strip().startswith("{") and "}{" in payload:
        raw_text = payload.strip()
        raw_chunks = re.findall(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", raw_text)
        all_cases = []
        for chunk in raw_chunks:
            try:
                sub_batch = parse_practice_bank(chunk)
                all_cases.extend(sub_batch.cases)
            except Exception:
                continue
        if all_cases:
            return ImportBatch(source="Import Multi-DP IA", cases=tuple(all_cases))

    # Cas où le payload est une liste d'examens/DP
    if isinstance(payload, list):
        all_cases = []
        for sub_item in payload:
            try:
                sub_batch = parse_practice_bank(sub_item)
                all_cases.extend(sub_batch.cases)
            except Exception:
                continue
        if all_cases:
            return ImportBatch(source="Import Liste DP IA", cases=tuple(all_cases))

    # Conversion support format UNESS / DP IA (schema_version ou metadata/questions/dp_context)
    if isinstance(payload, dict) and ("questions" in payload or "dp_context" in payload):
        title = payload.get("title", "Import DP")
        dp_ctx = payload.get("dp_context", {})
        stem = dp_ctx.get("enonce_general", payload.get("stem", "Énoncé du cas"))
        raw_qs = payload.get("questions", [])
        
        parsed_qs = []
        for q_idx, q in enumerate(raw_qs, start=1):
            prompt = q.get("enonce", q.get("prompt", f"Question {q_idx}"))
            explic = q.get("explication_ia", q.get("explanation", ""))
            
            # Reconstruction des propositions et de la bonne réponse
            props = q.get("propositions", [])
            choices = []
            correct_answers = []
            for p in props:
                p_id = str(p.get("id", "")).upper()
                p_txt = p.get("texte", "")
                choices.append(f"{p_id}. {p_txt}")
                if p.get("reponse_uness", p.get("verdict_ia", False)):
                    correct_answers.append(p_id)
            
            ans_str = ", ".join(correct_answers) if correct_answers else q.get("answer", "Vrai")
            parsed_qs.append(ImportedQuestion(
                prompt=prompt,
                answer=ans_str,
                explanation=explic,
                choices=tuple(choices)
            ))
            
        subj = payload.get("metadata", {}).get("subject", "")
        item_num = payload.get("metadata", {}).get("item_number", "")
        item_numbers = (str(item_num),) if item_num else _item_numbers(None, title, stem)
        status, review_reason = _case_status(item_numbers)
        
        canonical = json.dumps({"kind": "dp", "title": title, "stem": stem}, sort_keys=True, ensure_ascii=False)
        case = ImportedCase(
            fingerprint=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            external_id=f"dp-{hashlib.sha1(canonical.encode('utf-8')).hexdigest()[:12]}",
            kind="dp",
            title=title,
            stem=stem,
            item_numbers=item_numbers,
            questions=tuple(parsed_qs),
            status=status,
            review_reason=review_reason
        )
        return ImportBatch(source=str(payload.get("faculty") or "Import UNESS/IA").strip(), cases=(case,))

    if not isinstance(payload, dict) or (payload.get("version") != 1 and "cases" not in payload):
        raise ImportValidationError("Le format d'import attendu est JSON version 1 ou un format d'examen UNESS/DP")
    raw_cases = payload.get("cases", [payload] if "kind" in payload else [])
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ImportValidationError("Le fichier doit contenir au moins un cas")

    cases = []
    for index, raw_case in enumerate(raw_cases, start=1):
        if not isinstance(raw_case, dict):
            raise ImportValidationError(f"Cas {index} invalide")
        kind = _text(raw_case.get("kind"), f"cases[{index}].kind").lower()
        if kind not in {"dp", "kfp", "qcm"}:
            raise ImportValidationError(f"Cas {index} : le type doit être QCM, DP ou KFP")
        title = _text(raw_case.get("title"), f"cases[{index}].title")
        stem = _text(raw_case.get("stem"), f"cases[{index}].stem")
        raw_questions = raw_case.get("questions")
        if not isinstance(raw_questions, list) or not raw_questions:
            raise ImportValidationError(f"Cas {index} : questions absentes")
        questions = []
        for q_index, raw_question in enumerate(raw_questions, start=1):
            if not isinstance(raw_question, dict):
                raise ImportValidationError(f"Cas {index}, question {q_index} invalide")
            questions.append(ImportedQuestion(
                prompt=_text(raw_question.get("prompt"), f"cases[{index}].questions[{q_index}].prompt"),
                answer=_text(raw_question.get("answer"), f"cases[{index}].questions[{q_index}].answer"),
                explanation=_text(raw_question.get("explanation"), f"cases[{index}].questions[{q_index}].explanation"),
                choices=tuple(_text(choice, "choice") for choice in (raw_question.get("choices") or [])),
            ))
        item_numbers = _item_numbers(raw_case.get("item_numbers"), title, stem)
        external_id = str(raw_case.get("id") or f"case-{index}").strip()
        canonical = json.dumps({"kind": kind, "title": title, "stem": stem, "questions": [q.__dict__ for q in questions]}, sort_keys=True, ensure_ascii=False)
        status, review_reason = _case_status(item_numbers)
        cases.append(ImportedCase(
            fingerprint=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            external_id=external_id,
            kind=kind,
            title=title,
            stem=stem,
            item_numbers=item_numbers,
            questions=tuple(questions),
            status=status,
            review_reason=review_reason,
        ))
    return ImportBatch(source=str(payload.get("source") or "Import local").strip(), cases=tuple(cases))


def _discussion_text(payload: Any) -> str:
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8")
    if isinstance(payload, dict):
        messages = payload.get("messages") or payload.get("mapping")
        if isinstance(messages, dict):
            chunks = []
            for value in messages.values():
                message = value.get("message") if isinstance(value, dict) else None
                content = message.get("content") if isinstance(message, dict) else None
                if isinstance(content, dict):
                    parts = content.get("parts") or []
                    chunks.extend(str(part) for part in parts)
                elif content:
                    chunks.append(str(content))
            if chunks:
                return "\n".join(chunks)
        return json.dumps(payload, ensure_ascii=False)
    text = str(payload or "")
    if "<" in text and ">" in text:
        text = re.sub(r"<[^>]+>", "\n", text)
        text = html.unescape(text)
    return text


def parse_practice_discussion(payload: Any, *, source: str = "Discussion importée") -> ImportBatch:
    """Extrait une banque simple depuis une discussion ChatGPT exportée ou copiée."""
    text = _discussion_text(payload).replace("\r\n", "\n")
    blocks = list(re.finditer(r"(?im)^\s*(?:question|q)\s*(\d+)\s*[:.)-]\s*(.+?)(?=\n\s*(?:question|q)\s*\d+\s*[:.)-]|\Z)", text, re.S))
    if not blocks:
        raise ImportValidationError("Aucune question structurée trouvée dans la discussion")
    questions = []
    for block in blocks:
        content = block.group(2).strip()
        answer_match = re.search(r"(?is)\b(?:réponse|reponse|answer|correction)\s*[:：-]\s*(.+?)(?=\n\s*(?:explication|explanation|justification)\s*[:：-]|\Z)", content)
        if not answer_match:
            raise ImportValidationError(f"Réponse absente pour la question {block.group(1)}")
        explanation_match = re.search(r"(?is)\b(?:explication|explanation|justification)\s*[:：-]\s*(.+)$", content)
        answer = answer_match.group(1).strip()
        prompt = content[:answer_match.start()].strip()
        explanation = explanation_match.group(1).strip() if explanation_match else "Correction importée — validation recommandée."
        choices_match = re.search(r"(?im)(?:^|\n)\s*([A-D](?:\s*[).:-].*)?(?:\n\s*[A-D](?:\s*[).:-].*)?)+)", prompt)
        choices = tuple(line.strip() for line in choices_match.group(1).splitlines()) if choices_match else ()
        questions.append(ImportedQuestion(prompt=prompt, answer=answer, explanation=explanation, choices=choices))

    item_numbers = _item_numbers(None, text[:500], text[:1000])
    if re.search(r"\bKFP\b", text[:500], re.I):
        kind = "kfp"
    elif re.search(r"\bQCM\b|\bQRU\b|\bQRM\b|\bQRP\b", text[:500], re.I):
        kind = "qcm"
    else:
        kind = "dp"
    title = next((line.strip(" #:-") for line in text.splitlines() if line.strip()), f"Discussion {kind.upper()}")
    status, review_reason = _case_status(item_numbers)
    canonical = json.dumps({"kind": kind, "title": title, "stem": text[:500], "questions": [q.__dict__ for q in questions]}, sort_keys=True, ensure_ascii=False)
    case = ImportedCase(
        fingerprint=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        external_id=f"discussion-{hashlib.sha1(canonical.encode('utf-8')).hexdigest()[:12]}",
        kind=kind,
        title=title,
        stem=text[:500].strip(),
        item_numbers=item_numbers,
        questions=tuple(questions),
        status=status,
        review_reason=review_reason,
    )
    return ImportBatch(source=source, cases=(case,), raw_text=text)


def suggest_item_numbers(text: str, catalog: list[tuple[str, str]], limit: int = 5) -> list[tuple[str, float]]:
    """Classe les ITEM candidats par similarité textuelle, sans appel réseau."""
    normalized = re.sub(r"[^a-z0-9 ]", " ", text.lower())
    words = set(normalized.split())
    scored = []
    for number, title in catalog:
        candidate = re.sub(r"[^a-z0-9 ]", " ", str(title).lower())
        overlap = len(words & set(candidate.split())) / max(1, len(set(candidate.split())))
        score = round(100 * (0.65 * overlap + 0.35 * SequenceMatcher(None, normalized, candidate).ratio()), 1)
        scored.append((str(number), score))
    return sorted(scored, key=lambda row: row[1], reverse=True)[:limit]
