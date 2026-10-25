import { defineStore } from 'pinia'
import type { components } from '~/types/api'

// Код валюты (ISO): список валют задаётся в админке и приходит вместе с курсами
export type Currency = string

/**
 * Выбранная валюта отображения и курсы относительно USD.
 * Цены приходят из API в USD; пересчёт — только для показа, заказ фиксируется в USD.
 */
export const useCurrencyStore = defineStore('currency', () => {
  const cookie = useCookie<Currency>('maison_currency', {
    default: () => 'USD',
    maxAge: 60 * 60 * 24 * 365,
  })

  // Сколько единиц валюты за 1 USD — в порядке, заданном в админке
  const rates = ref<Record<Currency, number>>({ USD: 1 })
  const codes = computed(() => Object.keys(rates.value))

  async function load() {
    try {
      const data = await useApi()<components['schemas']['RatesOut']>('/currency/rates')
      rates.value = Object.fromEntries(Object.entries(data.rates).map(([code, rate]) => [code, Number(rate)]))
    } catch (error) {
      // Без курсов витрина продолжает работать в USD
      console.error('Failed to load exchange rates', error)
    }
  }

  const current = computed<Currency>(() => (rates.value[cookie.value] ? cookie.value : 'USD'))

  function set(currency: Currency) {
    cookie.value = currency
  }

  function convert(amountUsd: number): number {
    return amountUsd * (rates.value[current.value] ?? 1)
  }

  return { current, rates, codes, set, convert, load }
})
