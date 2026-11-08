@echo off
cd /d %~dp0
for %%t in (test_db test_templates test_export test_gui test_stress) do (
  python tests\%%t.py || exit /b 1
)
echo ALL OK
