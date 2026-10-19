<script setup lang="ts">
import { useAuthStore } from '~/stores/auth'

const { t } = useI18n()

// Вошедшему избранное показываем внутри кабинета, с навигацией по разделам
definePageMeta({
  middleware: () => {
    if (useAuthStore().isLoggedIn) return navigateTo(useLocalePath()('/account/wishlist'), { replace: true })
  },
})

useSeoMeta({ title: () => t('wishlist.title'), robots: 'noindex' })
</script>

<template>
  <UContainer class="py-10">
    <h1 class="border-b border-default pb-6 font-serif text-4xl md:text-5xl">{{ t('wishlist.title') }}</h1>
    <WishlistGrid grid-class="mt-8 md:grid-cols-3 lg:grid-cols-4" empty-class="py-24" />
  </UContainer>
</template>
