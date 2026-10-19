<script setup lang="ts">
import { useAuthStore } from '~/stores/auth'
import { useWishlistStore } from '~/stores/wishlist'
import type { ProductListItem, ProductPage } from '~/types/catalog'

// Список избранного — общий для страницы гостя и раздела кабинета
const props = defineProps<{ gridClass: string, emptyClass: string }>()

const { t, locale } = useI18n()
const api = useApi()
const localePath = useLocalePath()
const auth = useAuthStore()
const wishlist = useWishlistStore()

// Вошедшему — из аккаунта; гостю — товары по сохранённым в браузере slug
const { data: products } = await useAsyncData(
  'wishlist',
  async () => {
    if (auth.isLoggedIn) return wishlist.applyServer(await api<ProductListItem[]>('/account/wishlist'))
    if (!wishlist.slugs.length) return []
    const page = await api<ProductPage>('/catalog/products', { query: { slug: wishlist.slugs, page_size: 96 } })
    return page.items
  },
  { watch: [locale], default: () => [] },
)
// Убранные с этой страницы товары исчезают сразу
const visible = computed(() => products.value.filter((p) => wishlist.has(p.slug)))
</script>

<template>
  <div>
    <UAlert
      v-if="!auth.isLoggedIn && visible.length"
      :title="t('wishlist.guestHint')"
      :actions="[{ label: t('login.title'), to: localePath({ path: '/login', query: { redirect: '/account/wishlist' } }), color: 'neutral', variant: 'outline' }]"
      icon="i-lucide-info"
      color="neutral"
      variant="soft"
      class="mt-6"
    />

    <div v-if="visible.length" :class="['grid grid-cols-2 gap-x-4 gap-y-10', props.gridClass]">
      <CatalogProductCard v-for="product in visible" :key="product.slug" :product="product" />
    </div>
    <UEmpty
      v-else
      icon="i-lucide-heart"
      :title="t('wishlist.empty')"
      :description="t('wishlist.emptyHint')"
      :actions="[{ label: t('menu.all'), to: localePath('/watches'), color: 'neutral', variant: 'outline' }]"
      :class="props.emptyClass"
    />
  </div>
</template>
