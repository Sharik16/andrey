$(document).ready(function () {

    function postJSON(url, data, onSuccess, onError) {
        $.ajax({
            url: url,
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify(data || {})
        })
        .done(function (res) { onSuccess && onSuccess(res); })
        .fail(function (xhr) {
            const msg = (xhr.responseJSON && xhr.responseJSON.message)
                        || 'Ошибка запроса';
            alert(msg);
            onError && onError(xhr);
        });
    }

    // --- Сохранить баланс ---
    $(document).on('click', '[data-action="save-balance"]', function () {
        const $row  = $(this).closest('tr');
        const id    = $row.data('user-id');
        const value = parseInt($row.find('[data-balance-input]').val(), 10);

        if (isNaN(value) || value < 0) {
            alert('Баланс должен быть целым неотрицательным числом');
            return;
        }

        postJSON(`/admin/user/${id}/balance`, { balance: value }, function (res) {
            $row.find('[data-balance-input]').val(res.balance);
            flashRow($row, '#d4edda');
        });
    });

    // --- Назначить/снять админа ---
    $(document).on('click', '[data-action="toggle-admin"]', function () {
        const $row = $(this).closest('tr');
        const id   = $row.data('user-id');
        const $btn = $(this);

        $btn.prop('disabled', true);
        postJSON(`/admin/user/${id}/toggle_admin`, {}, function (res) {
            const isAdmin = res.is_admin === 1;
            const $badge  = $row.find('[data-role-badge]');
            $badge.text(isAdmin ? 'Админ' : 'Пользователь')
                  .toggleClass('admin', isAdmin)
                  .toggleClass('user', !isAdmin);
            $btn.text(isAdmin ? 'Разжаловать' : 'Назначить админом');
            flashRow($row, '#fff3cd');
        })
        .always(function () {
            $btn.prop('disabled', false);
        });
    });

    // --- Удалить пользователя ---
    $(document).on('click', '[data-action="delete"]', function () {
        const $row = $(this).closest('tr');
        const id   = $row.data('user-id');
        const name = $row.find('td').eq(1).text().trim();

        if (!confirm(`Удалить пользователя "${name}" (id=${id})? Действие необратимо.`))
            return;

        postJSON(`/admin/user/${id}/delete`, {}, function () {
            $row.fadeOut(250, function () { $(this).remove(); });
        });
    });

    // Вспышка цвета — визуальный фидбек
    function flashRow($row, color) {
        const original = $row.css('background-color');
        $row.css('background-color', color);
        setTimeout(function () {
            $row.css('background-color', original);
        }, 700);
    }
    
        // --- Сохранение цены AI ---
    $('#save-ai-price').on('click', function () {
        const price  = parseInt($('#ai-price-input').val(), 10);
        const $status = $('#ai-price-status');

        if (isNaN(price) || price < 0) {
            $status.removeClass('ok').addClass('err')
                   .text('Введите целое неотрицательное число');
            return;
        }

        postJSON('/admin/settings/ai_price', { price: price }, function (res) {
            $('#ai-price-input').val(res.price);
            $status.removeClass('err').addClass('ok')
                   .text('✓ Сохранено');
            setTimeout(function () { $status.text('').removeClass('ok'); }, 2000);
        }, function () {
            $status.removeClass('ok').addClass('err')
                   .text('Ошибка сохранения');
        });
    });
});