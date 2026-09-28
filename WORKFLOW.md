# Рабочий процесс

Репозиторий публичный: это витрина рабочего процесса. Секреты и данные заявок в него не попадают.

## Подключение на рабочем компьютере

1. Установить Git: https://git-scm.com/download/win
2. Войти в GitHub в браузере.
3. Клонировать репозиторий:

```powershell
git clone https://github.com/xxxmaxxxq/automation-requests.git
cd automation-requests
```

Если Git попросит вход, подтвердите доступ через окно GitHub.

## Как вносить изменения

Перед правками создавайте отдельную ветку:

```powershell
git checkout -b review/my-change
```

После правок:

```powershell
git status
git add -A
git commit -m "Describe the change"
git push -u origin review/my-change
```

Затем на GitHub откройте Pull Request из ветки `review/my-change` в `main`.

## Как делать ревью

1. Открыть вкладку Pull requests.
2. Выбрать нужный Pull Request.
3. Проверить вкладку Files changed.
4. Оставить комментарии к конкретным строкам.
5. Нажать Approve или Request changes.

## Как дать доступ другому человеку

В приватном репозитории нет безопасной "секретной ссылки", которая дает доступ без аккаунта. Правильный способ:

1. Открыть Settings.
2. Перейти в Collaborators / Access.
3. Нажать Invite collaborators.
4. Ввести GitHub username или email человека.
5. Выдать нужный уровень доступа.

Для работы и ревью обычно достаточно доступа `Write` или `Maintain`.

## Правила безопасности

- Не коммитить пароли, токены, cookies и персональные данные клиентов.
- Не хранить `.env` в Git.
- Перед отправкой изменений проверять `git status`.
- Основную ветку `main` держать рабочей.
