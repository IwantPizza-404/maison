export default defineAppConfig({
  ui: {
    colors: {
      primary: 'gold',
      neutral: 'stone',
    },
    button: {
      slots: {
        base: 'uppercase tracking-[0.18em] text-xs',
        // Длинные подписи переносятся, а не обрезаются: на телефоне иначе «Сообщить, когда буду…»
        label: 'whitespace-normal text-center',
      },
    },
    badge: {
      slots: {
        base: 'uppercase tracking-wider',
      },
    },
  },
})
