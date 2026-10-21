$(document).ready(function () {

    // ---------- РЕГИСТРАЦИЯ ----------
    $('#register-form').on('submit', function (e) {
        e.preventDefault();

        const pass     = $('#password').val();
        const passConf = $('#confirm_password').val();

        if (pass !== passConf) {
            alert('Пароли не совпадают');
            return;
        }
        if (pass.length < 6) {
            alert('Пароль должен быть не короче 6 символов');
            return;
        }

        $.ajax({
            url: '/user_register',
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({
                name:     $('#fullname').val(),
                lastname: $('#lastname').val(),
                email:    $('#email').val(),
                password: pass
            })
        })
        .done(function (res) {
            if (res.redirect) window.location.href = res.redirect;
        })
        .fail(function (xhr) {
            const msg = (xhr.responseJSON && xhr.responseJSON.message)
                        || 'Ошибка регистрации';
            alert(msg);
        });
    });

    // ---------- АВТОРИЗАЦИЯ ----------
    $('#login-form').on('submit', function (e) {
        e.preventDefault();

        $.ajax({
            url: '/user_login',
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({
                email:    $('#email').val(),
                password: $('#password').val()
            })
        })
        .done(function (res) {
            if (res.redirect) window.location.href = res.redirect;
        })
        .fail(function (xhr) {
            const msg = (xhr.responseJSON && xhr.responseJSON.message)
                        || 'Ошибка входа';
            alert(msg);
        });
    });

    // ---------- ИСТОРИЯ ТРАНЗАКЦИЙ (МОДАЛЬНОЕ ОКНО В /profile) ----------
    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    function renderTransactions(transactions) {
        const $content = $('#transactions-modal .modal-content');
        if (!transactions || transactions.length === 0) {
            $content.html(`
                <div class="tx-empty">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><path d="M8 12h8"/></svg>
                    <p>История операций пуста</p>
                </div>
            `);
            return;
        }

        let html = '<div class="tx-list">';
        transactions.forEach(function (tx) {
            const isPlus = tx.amount >= 0;
            const sign = tx.amount > 0 ? '+' : '';
            const cls = isPlus ? 'tx-in' : 'tx-out';
            const iconSvg = isPlus
                ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M5 12l7-7 7 7"/></svg>'
                : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M19 12l-7 7-7-7"/></svg>';

            html += `
                <div class="tx-item ${cls}">
                    <div class="tx-info-block">
                        <div class="tx-icon">${iconSvg}</div>
                        <div class="tx-text">
                            <span class="tx-desc">${escapeHtml(tx.description)}</span>
                            <span class="tx-date">${escapeHtml(tx.formatted_date || '')}</span>
                        </div>
                    </div>
                    <div class="tx-values">
                        <span class="tx-amount">${sign}${tx.amount} ₽</span>
                        <span class="tx-balance">Остаток: ${tx.balance_after} ₽</span>
                    </div>
                </div>
            `;
        });
        html += '</div>';
        $content.html(html);
    }

    $('#history-btn').on('click', function () {
        $('#transactions-modal').addClass('active');

        $.get('/api/transactions')
            .done(function (res) {
                if (res && res.transactions) {
                    renderTransactions(res.transactions);
                }
            });
    });

    $('#close-modal-btn').on('click', function () {
        $('#transactions-modal').removeClass('active');
    });

    $('#transactions-modal').on('click', function (e) {
        if (e.target === this) {
            $(this).removeClass('active');
        }
    });

    $(document).on('keydown', function (e) {
        if (e.key === 'Escape' && $('#transactions-modal').hasClass('active')) {
            $('#transactions-modal').removeClass('active');
        }
    });


    // ==========================================================
    // ============       ЧАТ С НЕЙРОСЕТЬЮ (/ai)       ==========
    // ==========================================================

    const $chatMessages = $('#chat-messages');
    let currentAttachedFile = null;

    // Прокрутка чата вниз
    function scrollChatToBottom(smooth = true) {
        if ($chatMessages.length) {
            $chatMessages.stop().animate({
                scrollTop: $chatMessages[0].scrollHeight
            }, smooth ? 250 : 0);
        }
    }
    scrollChatToBottom(false);

    // Авто-высота textarea
    const $textarea = $('#chat-prompt');
    $textarea.on('input', function () {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 140) + 'px';
    });

    // Отправка по Enter (без Shift)
    $textarea.on('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            $('#chat-form').trigger('submit');
        }
    });

    // Клик по подсказкам в приветственном экране
    $(document).on('click', '.suggestion-btn', function () {
        const text = $(this).data('prompt');
        $textarea.val(text).focus();
        $textarea.trigger('input');
    });

    // Прикрепление файла через кнопку скрепки
    $('#btn-attach').on('click', function () {
        $('#chat-file-input').val('').trigger('click');
    });

    // Выбор файла в input
    $('#chat-file-input').on('change', function () {
        if (this.files && this.files[0]) {
            handleSelectedFile(this.files[0]);
        }
    });

    function handleSelectedFile(file) {
        currentAttachedFile = file;
        $('#preview-filename').text(file.name);
        $('#chat-error-bar').hide();

        if (file.type.startsWith('image/')) {
            const reader = new FileReader();
            reader.onload = function (e) {
                $('#preview-thumb').attr('src', e.target.result).show();
                $('#preview-icon').hide();
            };
            reader.readAsDataURL(file);
        } else {
            $('#preview-thumb').hide();
            $('#preview-icon').show();
        }

        $('#attachment-preview-bar').css('display', 'flex');
        $textarea.focus();
    }

    // Удаление прикреплённого файла
    $('#btn-remove-attachment').on('click', function () {
        currentAttachedFile = null;
        $('#chat-file-input').val('');
        $('#attachment-preview-bar').hide();
        $('#preview-thumb').attr('src', '').hide();
    });

    // Drag & Drop файлов на контейнер чата
    const $dropzone = $('#chat-dropzone');
    const $dropOverlay = $('#drop-overlay');

    $dropzone.on('dragenter dragover', function (e) {
        e.preventDefault();
        e.stopPropagation();
        $dropOverlay.addClass('active');
    });

    $dropzone.on('dragleave drop', function (e) {
        e.preventDefault();
        e.stopPropagation();
        $dropOverlay.removeClass('active');
    });

    $dropzone.on('drop', function (e) {
        const dt = e.originalEvent.dataTransfer;
        if (dt && dt.files && dt.files.length) {
            handleSelectedFile(dt.files[0]);
        }
    });

    // Очистка истории чата
    $('#btn-clear-chat').on('click', function () {
        if (!confirm('Вы уверены, что хотите удалить всю историю переписки?')) {
            return;
        }

        $.post('/api/chat/clear')
            .done(function () {
                $chatMessages.html(`
                    <div class="chat-welcome" id="chat-welcome">
                        <div class="welcome-icon">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                            </svg>
                        </div>
                        <h3>История очищена</h3>
                        <p>Вы можете начать новый диалог, отправить текст, фото или аудиозапись.</p>
                        <div class="welcome-suggestions">
                            <button class="suggestion-btn" type="button" data-prompt="Расскажи короткую интересную историю">💡 «Расскажи короткую интересную историю»</button>
                            <button class="suggestion-btn" type="button" data-prompt="Помоги составить план тренировок на неделю">🏃‍♂️ «Помоги составить план тренировок на неделю»</button>
                        </div>
                    </div>
                `);
            })
            .fail(function (xhr) {
                alert((xhr.responseJSON && xhr.responseJSON.message) || 'Ошибка очистки чата');
            });
    });

    // Генерация HTML сообщения
    function buildMessageHtml(msg) {
        let attachmentHtml = '';
        if (msg.file_url) {
            if (msg.file_type === 'image') {
                attachmentHtml = `
                    <div class="msg-attachment">
                        <a href="${escapeHtml(msg.file_url)}" target="_blank">
                            <img class="msg-img" src="${escapeHtml(msg.file_url)}" alt="Вложение" loading="lazy">
                        </a>
                    </div>
                `;
            } else if (msg.file_type === 'audio') {
                attachmentHtml = `
                    <div class="msg-attachment">
                        <audio class="msg-audio" controls src="${escapeHtml(msg.file_url)}"></audio>
                    </div>
                `;
            }
        }

        const avatarHtml = msg.role === 'assistant'
            ? `<div class="msg-avatar">
                   <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a2 2 0 0 1 2 2v2a2 2 0 0 1-2 2 2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z"/><rect x="4" y="8" width="16" height="12" rx="4"/><circle cx="9" cy="13" r="1" fill="currentColor"/><circle cx="15" cy="13" r="1" fill="currentColor"/></svg>
               </div>`
            : '';

        const textHtml = msg.content ? `<div class="msg-text">${escapeHtml(msg.content)}</div>` : '';
        const timeHtml = msg.time ? `<div class="msg-time">${escapeHtml(msg.time)}</div>` : '';

        return `
            <div class="msg-row ${msg.role}">
                ${avatarHtml}
                <div class="msg-bubble">
                    ${attachmentHtml}
                    ${textHtml}
                    ${timeHtml}
                </div>
            </div>
        `;
    }

    // Отправка формы чата
    $('#chat-form').on('submit', function (e) {
        e.preventDefault();

        const prompt = $textarea.val().trim();
        if (!prompt && !currentAttachedFile) {
            return;
        }

        const $btn = $('#chat-send-btn');
        const $errorBar = $('#chat-error-bar');
        $errorBar.hide();

        // Удаляем приветственный экран при первой отправке
        $('#chat-welcome').remove();

        // Индикатор набора сообщения
        const typingId = 'typing-' + Date.now();
        const typingHtml = `
            <div class="msg-row assistant" id="${typingId}">
                <div class="msg-avatar">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="8" width="16" height="12" rx="4"/></svg>
                </div>
                <div class="msg-bubble">
                    <div class="typing-indicator">
                        <span class="typing-dot"></span>
                        <span class="typing-dot"></span>
                        <span class="typing-dot"></span>
                    </div>
                </div>
            </div>
        `;

        // Формируем FormData для отправки текста и файла
        const formData = new FormData();
        formData.append('prompt', prompt);
        if (currentAttachedFile) {
            formData.append('file', currentAttachedFile);
        }

        // Блокируем кнопку и поле ввода
        $btn.prop('disabled', true);

        // 1. СРАЗУ отображаем сообщение пользователя в чате
        const now = new Date();
        const timeStr = String(now.getHours()).padStart(2, '0') + ':' + String(now.getMinutes()).padStart(2, '0');

        let fileType = null;
        let fileUrl = null;
        if (currentAttachedFile) {
            fileUrl = URL.createObjectURL(currentAttachedFile);
            if (currentAttachedFile.type.startsWith('image/')) {
                fileType = 'image';
            } else if (currentAttachedFile.type.startsWith('audio/')) {
                fileType = 'audio';
            } else {
                fileType = 'file';
            }
        }

        const optimisticUserMsg = {
            role: 'user',
            content: prompt,
            file_url: fileUrl,
            file_type: fileType,
            time: timeStr
        };
        $chatMessages.append(buildMessageHtml(optimisticUserMsg));

        // 2. Добавляем индикатор набора под сообщением пользователя
        $chatMessages.append(typingHtml);
        scrollChatToBottom();

        // Очищаем форму и вложение
        const attachedToSend = currentAttachedFile;
        const promptToSend = prompt;
        $textarea.val('').trigger('input');
        $('#btn-remove-attachment').trigger('click');

        $.ajax({
            url: '/ai_request',
            method: 'POST',
            data: formData,
            processData: false,
            contentType: false
        })
        .done(function (res) {
            $('#' + typingId).remove();

            // Добавляем ответ нейросети
            if (res.assistant_message) {
                $chatMessages.append(buildMessageHtml(res.assistant_message));
            }

            if (typeof res.balance !== 'undefined') {
                $('#balance-value').text(res.balance);
            }

            scrollChatToBottom();
        })
        .fail(function (xhr) {
            $('#' + typingId).remove();

            // Восстанавливаем текст, если отправка сорвалась
            $textarea.val(promptToSend).trigger('input');
            if (attachedToSend) {
                handleSelectedFile(attachedToSend);
            }

            const msg = (xhr.responseJSON && xhr.responseJSON.message) || 'Ошибка при отправке запроса';
            $errorBar.text(msg).show();
            scrollChatToBottom();
        })
        .always(function () {
            $btn.prop('disabled', false);
            $textarea.focus();
        });
    });

});
