// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  devtools: { enabled: true },

  // @nuxt/ui подключает Tailwind, @nuxt/fonts и @nuxt/icon
  modules: ['@nuxt/ui', '@nuxtjs/i18n', '@pinia/nuxt', '@nuxt/eslint'],

  css: ['~/assets/css/main.css'],

  runtimeConfig: {
    // Адрес API для серверного рендеринга (внутри сети) — NUXT_API_BASE
    apiBase: 'http://localhost:8000/api/v1',
    // Разрешить индексацию поисковиками — только на продакшене (NUXT_INDEXABLE=true)
    indexable: false,
    public: {
      // Адрес API для браузера — NUXT_PUBLIC_API_BASE
      apiBase: 'http://localhost:8000/api/v1',
      siteUrl: 'https://maison.uz',
    },
  },

  ui: {
    // Единый фирменный вид без тёмной темы
    colorMode: false,
  },

  fonts: {
    families: [
      { name: 'Cormorant Garamond', provider: 'google', weights: [400, 500, 600] },
      { name: 'Inter', provider: 'google', weights: [400, 500] },
    ],
  },

  i18n: {
    baseUrl: 'https://maison.uz',
    defaultLocale: 'en',
    strategy: 'prefix_except_default',
    langDir: 'locales',
    locales: [
      { code: 'en', language: 'en-US', name: 'English', file: 'en.json' },
      { code: 'uz', language: 'uz-Latn-UZ', name: 'O‘zbekcha', file: 'uz.json' },
      { code: 'ru', language: 'ru-RU', name: 'Русский', file: 'ru.json' },
    ],
    detectBrowserLanguage: {
      useCookie: true,
      cookieKey: 'maison_locale',
      redirectOn: 'root',
    },
  },

  app: {
    head: {
      titleTemplate: '%s · Maison',
      // Значок: SVG для современных браузеров, ICO — для старых, PNG — для iOS и Android
      link: [
        { rel: 'icon', type: 'image/svg+xml', href: '/favicon.svg' },
        { rel: 'icon', href: '/favicon.ico', sizes: '48x48' },
        { rel: 'apple-touch-icon', href: '/apple-touch-icon.png' },
        { rel: 'manifest', href: '/site.webmanifest' },
      ],
      meta: [{ name: 'theme-color', content: '#0d0d0d' }],
    },
  },

  typescript: {
    strict: true,
  },
})
