import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import './theme.css'
import App from './App.vue'
import Login from './views/Login.vue'

// Apply saved theme before mount
const savedTheme = localStorage.getItem('theme')
if (savedTheme) document.documentElement.setAttribute('data-theme', savedTheme)

const token = localStorage.getItem('token')

const RootComponent = token ? App : Login
const app = createApp(RootComponent)

app.use(ElementPlus)
app.mount('#app')
