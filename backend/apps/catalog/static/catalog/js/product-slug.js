// Превью slug нового товара: пока поле пустое, в нём серым показано, каким slug станет
// при сохранении — бренд + английское название (tissot-prx-200). Сам slug строит сервер:
// он же добавляет номер, если такой уже занят. Вписанный вручную slug сохраняется как есть.
// У существующих товаров slug не трогаем — по нему открываются ссылки на товар.
document.addEventListener("DOMContentLoaded", () => {
  const slug = document.getElementById("id_slug")
  const name = document.getElementById("id_name_en")
  const brand = document.getElementById("id_brand")
  if (!slug || !name || !brand || !window.location.pathname.endsWith("/add/")) return

  const preview = () => {
    const brandName = brand.selectedOptions[0]?.value ? brand.selectedOptions[0].text : ""
    slug.placeholder = window.URLify(`${brandName} ${name.value}`, 200)
  }

  name.addEventListener("input", preview)
  // Бренд выбирается через автодополнение (select2) — оно сообщает о выборе через jQuery
  const $ = window.django && window.django.jQuery
  if ($) $(brand).on("change", preview)
  else brand.addEventListener("change", preview)
  preview()
})
