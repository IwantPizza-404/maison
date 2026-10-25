import { useCurrencyStore } from '~/stores/currency'

const LOCALE_FORMATS: Record<string, string> = { en: 'en-US', ru: 'ru-RU', uz: 'uz-Latn-UZ' }

/** Форматирует цену из USD (строка из API) в выбранную валюту и язык. */
export function useMoney() {
  const currency = useCurrencyStore()
  const { locale } = useI18n()

  function format(amountUsd: string | number | null | undefined): string {
    if (amountUsd === null || amountUsd === undefined) return ''
    return formatIn(currency.convert(Number(amountUsd)), currency.current)
  }

  /** Сумма в конкретной валюте — например, по курсу, зафиксированному в заказе. */
  function formatIn(value: number, code: string): string {
    const formatted = new Intl.NumberFormat(LOCALE_FORMATS[locale.value] ?? 'en-US', {
      style: 'currency',
      currency: code,
      // Цены часов показываем без копеек; сумы дополнительно округляем до тысяч.
      // Маленькие суммы (валюта с курсом меньше единицы) — с копейками, иначе было бы «0»
      maximumFractionDigits: Math.abs(value) < 100 ? 2 : 0,
    }).format(code === 'UZS' ? Math.round(value / 1000) * 1000 : value)
    // В русской локали Intl не знает сокращения для сума
    return locale.value === 'ru' ? formatted.replace('UZS', 'сум') : formatted
  }

  return { format, formatIn }
}
