"""Тест параллельной выдачи seq.

Обычный ``pytest.mark.django_db`` оборачивает тест в транзакцию, а транзакция
не видна из другого потока — поэтому здесь ``transaction=True`` и каждая нить
закрывает своё соединение с базой по завершении.

Что именно проверяется: ``UPDATE ... RETURNING`` в ``allocate_seq`` держит
блокировку строки чата до коммита. Без неё два потока прочитали бы одинаковый
``last_seq``, и второй получил бы IntegrityError от ``uniq_message_seq``.
"""

from __future__ import annotations

import threading

import pytest
from django.contrib.auth import get_user_model
from django.db import connections

from apps.chats.models import Chat, ChatMember
from apps.messaging.models import Message
from apps.messaging.services import append_message

User = get_user_model()

THREADS = 8
PER_THREAD = 5


@pytest.mark.django_db(transaction=True)
def test_parallel_sending_produces_contiguous_unique_seq():
    alice = User.objects.create_user(username="parallel_alice", password="bolshoy-parol-2026")
    bob = User.objects.create_user(username="parallel_bob", password="bolshoy-parol-2026")
    chat = Chat.objects.create(
        type=Chat.Type.DIRECT, direct_key=Chat.build_direct_key(alice.pk, bob.pk)
    )
    ChatMember.objects.create(chat=chat, user=alice)
    ChatMember.objects.create(chat=chat, user=bob)

    errors: list[BaseException] = []
    barrier = threading.Barrier(THREADS)

    def worker(index: int) -> None:
        try:
            barrier.wait(timeout=10)  # все начинают одновременно
            for step in range(PER_THREAD):
                append_message(chat, alice, f"нить {index}, шаг {step}")
        except BaseException as exc:
            errors.append(exc)
        finally:
            # Соединение принадлежит потоку, и без закрытия тест повиснет
            # на уборке: Postgres держит открытые бэкенды.
            connections.close_all()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not errors, f"Сбои при параллельной отправке: {errors}"

    total = THREADS * PER_THREAD
    seqs = list(Message.objects.filter(chat=chat).order_by("seq").values_list("seq", flat=True))
    assert len(seqs) == total
    # Непрерывный диапазон без дыр и повторов — именно то, что даёт блокировка
    # строки в UPDATE ... RETURNING.
    assert seqs == list(range(1, total + 1))

    chat.refresh_from_db()
    assert chat.last_seq == total


@pytest.mark.django_db(transaction=True)
def test_parallel_duplicates_keep_single_message():
    """Два потока отправляют один client_msg_id — должен остаться один."""
    import uuid

    alice = User.objects.create_user(username="dup_alice", password="bolshoy-parol-2026")
    bob = User.objects.create_user(username="dup_bob", password="bolshoy-parol-2026")
    chat = Chat.objects.create(
        type=Chat.Type.DIRECT, direct_key=Chat.build_direct_key(alice.pk, bob.pk)
    )
    ChatMember.objects.create(chat=chat, user=alice)
    ChatMember.objects.create(chat=chat, user=bob)

    client_id = uuid.uuid4()
    errors: list[BaseException] = []
    barrier = threading.Barrier(THREADS)

    def worker() -> None:
        try:
            barrier.wait(timeout=10)
            append_message(chat, alice, "один и тот же текст", client_id)
        except BaseException as exc:
            errors.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker) for _ in range(THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not errors, f"Сбои при параллельной отправке дубля: {errors}"
    assert Message.objects.filter(chat=chat).count() == 1
    chat.refresh_from_db()
    # Откатившиеся транзакции не должны оставить дыр в нумерации.
    assert chat.last_seq == 1
