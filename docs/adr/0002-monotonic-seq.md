# 0002. Монотонный `seq` вместо сортировки по времени

**Статус:** принято
**Дата:** 2026-10-22

## Контекст

Лента сообщений должна:

- быть стабильно упорядоченной при пагинации;
- отдавать «непрочитанные» без отдельного счётчика;
- выдерживать 1000+ сообщений в секунду при массовой вставке.

Первое, что приходит в голову, — сортировать по `created_at` и листать
`WHERE created_at < :cursor`. У этого варианта два дефекта:

1. **Одинаковые timestamp.** `now()` в PostgreSQL возвращает время начала транзакции.
   При пачке вставок внутри одной транзакции у всех сообщений будет одно и то же
   значение — порядок между ними не определён, и пагинация начнёт дублировать или
   терять строки.
2. **Счётчик непрочитанного.** Пришлось бы держать отдельную таблицу прочтений и
   считать её агрегатом на каждый запрос списка чатов.

## Решение

В каждой строке `Message` хранится `seq` — целое, монотонное **внутри чата**.

```python
class Message(models.Model):
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name="messages")
    seq = models.BigIntegerField()
    client_msg_id = models.UUIDField()
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["chat", "seq"], name="uniq_chat_seq"),
            models.UniqueConstraint(
                fields=["chat", "client_msg_id"], name="uniq_chat_client_msg_id"
            ),
        ]
        ordering = ["chat_id", "seq"]
```

Выдача следующего значения — под блокировкой строки чата, в той же транзакции, что и
вставка:

```python
with transaction.atomic():
    chat = Chat.objects.select_for_update().get(pk=chat_id)
    chat.last_seq += 1
    chat.save(update_fields=["last_seq"])
    message = Message.objects.create(chat=chat, seq=chat.last_seq, ...)
```

Курсор пагинации — сам `seq`: `WHERE chat_id = :id AND seq < :cursor ORDER BY seq DESC
LIMIT 50`. Дубликатов и пропусков быть не может, потому что значения уникальны.

Непрочитанное считается разностью: `chat.last_seq - member.last_read_seq`.

## Последствия

- Плюс: пагинация корректна при любой скорости вставки.
- Плюс: непрочитанные — одно вычитание, без агрегатов и фоновых пересчётов.
- Плюс: `seq` же служит курсором для recovery в Centrifugo — после реконнекта клиент
  просит историю «после моего последнего seq».
- Минус: `SELECT ... FOR UPDATE` сериализует записи **внутри одного чата**. Для
  мессенджера это естественное ограничение: два сообщения в один чат не обязаны
  вставляться параллельно, а разные чаты не мешают друг другу.
- Минус: при очень горячем чате блокировка становится точкой конкуренции. Если
  упрёмся — перейдём на отдельную последовательность на чат; пока нагрузочный тест
  этого не требует.
