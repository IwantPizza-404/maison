// Вкладки языков (modeltranslation) в Unfold: открываем вкладку с ошибкой и помечаем её.
// Сам modeltranslation ищет класс .errors у строки поля, как в стандартной админке, —
// в разметке Unfold его нет, и ошибка (например, пустое английское название) пряталась
// на неактивной вкладке.
function showTranslationErrors($, container) {
  const $container = $(container)
  const withErrors = $container
    .children("div[id]")
    .toArray()
    .map((panel, index) => ($(panel).find(".errorlist").length ? index : -1))
    .filter((index) => index >= 0)
  if (!withErrors.length) return

  const $tabs = $container.find("> ul > li")
  withErrors.forEach((index) => $tabs.eq(index).addClass("ui-tab-has-errors").css("outline", "2px solid #dc2626"))
  $container.tabs("option", "active", withErrors[0])
}

// Вкладки создаются уже после загрузки страницы — ловим событие создания каждого блока.
// jQuery — тот же экземпляр, что у modeltranslation (с jQuery UI).
document.addEventListener("DOMContentLoaded", () => {
  const $ = window.jQuery || (window.django && window.django.jQuery)
  if (!$) return
  $(".ui-tabs").each((_, container) => showTranslationErrors($, container))
  $(document).on("tabscreate", (event) => setTimeout(() => showTranslationErrors($, event.target)))
})
