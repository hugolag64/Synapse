from unittest.mock import Mock

from backend.core.ai.routing import AIImageContent, AIModel, AIResponse, AITask
from backend.core.ai.tasks import (
    extract_grid,
    generate_dp,
    generate_ecos,
    generate_kfp,
    generate_qcm,
    generate_uness_correction,
)


def _service():
    service = Mock()
    service.generate.return_value = AIResponse("{}", AIModel.FLASH)
    return service


def test_generate_qcm_uses_json_lite_route():
    service = _service()
    generate_qcm("qcm", service=service)
    service.generate.assert_called_once_with(AITask.QCM, "qcm", response_format="json")


def test_generate_ecos_selects_lite_or_flash_by_complexity():
    service = _service()
    generate_ecos("simple", service=service)
    generate_ecos("complexe", complex_case=True, service=service)
    assert service.generate.call_args_list[0].args[0] is AITask.ECOS_SIMPLE
    assert service.generate.call_args_list[1].args[0] is AITask.ECOS_COMPLEX


def test_generate_dp_and_kfp_use_flash_json_route():
    service = _service()
    generate_dp("dp", service=service)
    generate_kfp("kfp", service=service)
    assert service.generate.call_args_list[0].args[0] is AITask.DP
    assert service.generate.call_args_list[1].args[0] is AITask.KFP
    assert all(call.kwargs["response_format"] == "json" for call in service.generate.call_args_list)


def test_extract_grid_marks_result_for_human_validation():
    service = _service()
    result = extract_grid("grille", service=service)
    assert result.response.text == "{}"
    assert result.requires_human_validation is True
    service.generate.assert_called_once_with(
        AITask.EXTRACTION_GRILLE, "grille", response_format="json"
    )


def test_generate_uness_correction_uses_flash_json_route_and_forwards_images():
    service = _service()
    images = (AIImageContent(mime_type="image/png", data=b"fixture"),)

    generate_uness_correction("corrige ce quiz", images=images, service=service)

    service.generate.assert_called_once_with(
        AITask.UNESS_CORRECTION,
        "corrige ce quiz",
        response_format="json",
        images=images,
    )


def test_generate_uness_correction_defaults_to_no_images():
    service = _service()

    generate_uness_correction("corrige ce quiz", service=service)

    service.generate.assert_called_once_with(
        AITask.UNESS_CORRECTION,
        "corrige ce quiz",
        response_format="json",
        images=(),
    )
