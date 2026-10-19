<script setup lang="ts">
const { locale, locales, t, setLocaleCookie } = useI18n()
const switchLocalePath = useSwitchLocalePath()
</script>

<template>
  <nav :aria-label="t('language')" class="flex gap-1">
    <!-- Ссылка сама cookie не меняет: без этого переход на английский (корень без префикса)
         возвращал на язык из cookie через detectBrowserLanguage -->
    <UButton
      v-for="item in locales"
      :key="item.code"
      :to="switchLocalePath(item.code)"
      :label="item.code"
      variant="link"
      size="sm"
      :class="item.code === locale ? 'text-gold-500' : 'text-white/70 hover:text-white'"
      @click="setLocaleCookie(item.code)"
    />
  </nav>
</template>
