<script setup lang="ts">
defineProps<{ title?: string; subtitle?: string; to?: string; linkLabel?: string }>()
</script>

<template>
  <!-- Ссылка — в одном ряду с заголовком, подзаголовок — под ними: иначе длинный подзаголовок
       на телефоне сталкивает ссылку вниз -->
  <div v-if="title" class="mb-8">
    <div class="flex items-center justify-between gap-4">
      <h2 class="min-w-0 font-serif text-3xl md:text-4xl">{{ title }}</h2>
      <UButton
        v-if="to && linkLabel"
        :to="to"
        :label="linkLabel"
        trailing-icon="i-lucide-arrow-right"
        variant="link"
        color="neutral"
        class="shrink-0"
      />
    </div>
    <p v-if="subtitle" class="mt-2 text-muted">{{ subtitle }}</p>
  </div>
</template>
