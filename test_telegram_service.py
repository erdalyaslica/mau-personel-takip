import unittest
from unittest.mock import patch

import telegram_service as service


class ServiceTests(unittest.TestCase):
    def test_control_reports_and_persists_changes(self):
        old = [{"Ad": "Eski", "Soyad": "Kişi", "Birim": "A", "E-posta": "old@example.com"}]
        new = [{"Ad": "Yeni", "Soyad": "Kişi", "Birim": "B", "E-posta": "new@example.com"}]
        with patch.object(service, "send") as send, patch.object(
            service, "read_state", side_effect=[(old, "sha"), (old, "sha")]
        ), patch.object(service.mau_rehber, "fetch_personnel", return_value=new), patch.object(
            service, "write_state"
        ) as write:
            service.control("token", "chat")
        write.assert_called_once_with(new, "sha")
        self.assertIn("başladı", send.call_args_list[0].args[2])
        self.assertIn("Yeni: 1", send.call_args_list[1].args[2])
        self.assertIn("Ayrılan: 1", send.call_args_list[1].args[2])

    def test_control_failure_sends_completion_error(self):
        with patch.object(service, "send") as send, patch.object(
            service, "read_state", side_effect=RuntimeError("GitHub failed")
        ):
            service.control("token", "chat")
        self.assertIn("tamamlanamadı", send.call_args_list[-1].args[2])

    def test_recent_uses_git_history(self):
        row = "+,Ali,Veli,Birim,Görev,ali@example.com,123"
        with patch.object(service, "github", side_effect=[
            [{"sha": "abc", "commit": {"committer": {"date": "2026-09-26T09:00:00Z"}}}],
            {"files": [{"filename": "rehber_durumu.csv", "patch": "@@ -0,0 +1 @@\n" + row}]},
        ]):
            message = service.recent_text()
        self.assertIn("Ali Veli", message)
        self.assertIn("Yeni", message)


if __name__ == "__main__":
    unittest.main()
