from unittest.mock import patch

from src.app import _cmd_autorizar


def test_autorizar_usuario_valido():
    with patch("src.app.authorize", return_value="✅ ok") as mock_auth, \
         patch("src.app.get_user_nome", return_value="Admin"):
        _cmd_autorizar("5511999 ; João ; Dev ; SP", admin_phone="5511000")

    mock_auth.assert_called_once_with(
        phone="5511999",
        nome="João",
        cargo="Dev",
        casa="SP",
        added_by_tel="5511000",
        added_by_nome="Admin",
        admin=False,
    )


def test_autorizar_com_flag_admin():
    with patch("src.app.authorize", return_value="✅ ok") as mock_auth, \
         patch("src.app.get_user_nome", return_value="Admin"):
        _cmd_autorizar("5511999 ; João ; Dev ; SP ; admin", admin_phone="5511000")

    assert mock_auth.call_args.kwargs["admin"] is True


def test_autorizar_sem_flag_admin():
    with patch("src.app.authorize", return_value="✅ ok") as mock_auth, \
         patch("src.app.get_user_nome", return_value="Admin"):
        _cmd_autorizar("5511999 ; João ; Dev ; SP ; user", admin_phone="5511000")

    assert mock_auth.call_args.kwargs["admin"] is False


def test_autorizar_campos_insuficientes_retorna_aviso():
    result = _cmd_autorizar("5511999 ; João", admin_phone="5511000")
    assert "⚠️" in result


def test_autorizar_args_vazios_retorna_aviso():
    result = _cmd_autorizar("", admin_phone="5511000")
    assert "⚠️" in result


def test_autorizar_espaco_nos_campos_e_removido():
    with patch("src.app.authorize", return_value="✅ ok") as mock_auth, \
         patch("src.app.get_user_nome", return_value="Admin"):
        _cmd_autorizar("  5511999  ;  João  ;  Dev  ;  SP  ", admin_phone="5511000")

    assert mock_auth.call_args.kwargs["nome"] == "João"
    assert mock_auth.call_args.kwargs["phone"] == "5511999"
