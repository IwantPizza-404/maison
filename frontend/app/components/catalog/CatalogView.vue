<script setup lang="ts">
import type { CatalogFilters, ProductPage, SortOption } from '~/types/catalog'

/** Каталог с фильтрами. На странице бренда бренд зафиксирован и фильтр по бренду скрыт. */
const props = defineProps<{ title: string; brand?: string }>()

const { t, locale } = useI18n()
const api = useApi()
const catalog = useCatalogQuery({ brand: props.brand })
const key = props.brand ? `:${props.brand}` : ''

const [{ data: filters }, { data: products, status }] = await Promise.all([
  useAsyncData(`catalog-filters${key}`, () => api<CatalogFilters>('/catalog/filters', { query: { brand: props.brand } }), { watch: [locale] }),
  useAsyncData(`catalog-products${key}`, () => api<ProductPage>('/catalog/products', { query: catalog.apiQuery.value }), {
    watch: [catalog.apiQuery, locale],
  }),
])

const filtersOpen = ref(false)
const route = useRoute()
watch(() => route.query, () => (filtersOpen.value = false))

const sortItems = computed<{ value: SortOption; label: string }[]>(() => [
  { value: 'newest', label: t('catalog.sort.newest') },
  { value: 'price_asc', label: t('catalog.sort.priceAsc') },
  { value: 'price_desc', label: t('catalog.sort.priceDesc') },
])

const sort = computed({
  get: () => catalog.sort.value,
  set: (value: SortOption) => catalog.setSort(value),
})

const page = computed({
  get: () => catalog.page.value,
  set: (value: number) => {
    catalog.setPage(value)
    if (import.meta.client) window.scrollTo({ top: 0, behavior: 'smooth' })
  },
})
</script>

<template>
  <UContainer class="py-10">
    <header class="flex flex-wrap items-end justify-between gap-4 border-b border-default pb-6">
      <div>
        <slot name="heading">
          <h1 class="font-serif text-4xl md:text-5xl">{{ title }}</h1>
        </slot>
        <p class="mt-2 text-sm text-muted">{{ t('catalog.found', { n: products?.count ?? 0 }) }}</p>
      </div>

      <!-- На телефоне — во всю ширину: фильтры слева, сортировка занимает остальное -->
      <div class="flex w-full items-center gap-3 sm:w-auto">
        <USlideover v-if="filters" v-model:open="filtersOpen" side="left" :title="t('filters.title')" class="lg:hidden">
          <UButton
            :label="t('filters.title')"
            icon="i-lucide-sliders-horizontal"
            color="neutral"
            variant="outline"
            class="shrink-0 lg:hidden"
          >
            <template v-if="catalog.activeCount.value" #trailing>
              <UBadge :label="String(catalog.activeCount.value)" size="sm" />
            </template>
          </UButton>
          <template #body>
            <CatalogFilters :filters="filters" :hide-brand="!!brand" hide-title />
          </template>
        </USlideover>

        <USelect v-model="sort" :items="sortItems" :aria-label="t('catalog.sort.label')" class="min-w-0 flex-1 sm:w-52 sm:flex-none" />
      </div>
    </header>

    <div class="mt-8 grid gap-10 lg:grid-cols-[240px_1fr]">
      <aside v-if="filters" class="hidden lg:block">
        <CatalogFilters :filters="filters" :hide-brand="!!brand" />
      </aside>

      <section :class="{ 'opacity-50 transition-opacity': status === 'pending' }">
        <div v-if="products?.items.length" class="grid grid-cols-2 gap-x-4 gap-y-10 md:grid-cols-3">
          <CatalogProductCard v-for="product in products.items" :key="product.slug" :product="product" />
        </div>

        <UEmpty
          v-else-if="status !== 'pending'"
          icon="i-lucide-search-x"
          :title="t('catalog.empty')"
          :actions="[{ label: t('filters.reset'), color: 'neutral', variant: 'outline', onClick: () => catalog.reset() }]"
          class="py-24"
        />

        <div v-if="products && products.count > PAGE_SIZE" class="mt-12 flex justify-center">
          <UPagination v-model:page="page" :total="products.count" :items-per-page="PAGE_SIZE" color="neutral" active-color="neutral" />
        </div>
      </section>
    </div>
  </UContainer>
</template>
