<script setup lang="ts">
import type { NavigationMenuItem } from '@nuxt/ui'
import { useAuthStore } from '~/stores/auth'

definePageMeta({ middleware: 'auth' })

const { t } = useI18n()
const localePath = useLocalePath()
const auth = useAuthStore()

const items = computed<NavigationMenuItem[]>(() => [
  { label: t('account.nav.overview'), icon: 'i-lucide-layout-grid', to: localePath('/account'), exact: true },
  { label: t('account.nav.orders'), icon: 'i-lucide-package', to: localePath('/account/orders') },
  { label: t('account.nav.wishlist'), icon: 'i-lucide-heart', to: localePath('/account/wishlist') },
  { label: t('account.nav.collection'), icon: 'i-lucide-watch', to: localePath('/account/collection') },
  { label: t('account.nav.alerts'), icon: 'i-lucide-bell', to: localePath('/account/alerts') },
  { label: t('account.nav.requests'), icon: 'i-lucide-search', to: localePath('/account/requests') },
  { label: t('account.nav.profile'), icon: 'i-lucide-user', to: localePath('/account/profile') },
])

async function logout() {
  await auth.logout()
  await navigateTo(localePath('/'))
}

useSeoMeta({ robots: 'noindex' })

// На телефоне разделы прокручиваются вбок — показываем активный, а не первые три
const route = useRoute()
const mobileNav = useTemplateRef<HTMLElement>('mobileNav')
function revealActive() {
  mobileNav.value?.querySelector('[data-active]')?.scrollIntoView({ inline: 'center', block: 'nearest' })
}
onMounted(revealActive)
watch(() => route.path, () => nextTick(revealActive))
</script>

<template>
  <UContainer class="py-10">
    <header class="flex flex-wrap items-end justify-between gap-4 border-b border-default pb-6">
      <div>
        <p class="text-xs uppercase tracking-[0.2em] text-muted">{{ t('account.title') }}</p>
        <h1 class="mt-1 font-serif text-4xl">{{ auth.customer?.name || auth.customer?.phone }}</h1>
      </div>
      <UButton :label="t('account.logout')" icon="i-lucide-log-out" variant="link" color="neutral" @click="logout" />
    </header>

    <div class="mt-8 grid gap-10 lg:grid-cols-[220px_1fr]">
      <UNavigationMenu
        :items="items"
        orientation="vertical"
        variant="link"
        color="neutral"
        class="hidden lg:flex"
        :ui="{ link: 'py-2 data-active:text-gold-700' }"
      />
      <!-- На телефоне — горизонтальная прокрутка разделов -->
      <div ref="mobileNav" class="-mx-4 overflow-x-auto px-4 lg:hidden">
        <UNavigationMenu :items="items" variant="pill" color="neutral" :ui="{ list: 'w-max' }" />
      </div>

      <section>
        <NuxtPage />
      </section>
    </div>
  </UContainer>
</template>
