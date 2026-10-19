package com.brickindex.app.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.brickindex.app.AppViewModel

@Composable
fun AboutScreen(vm: AppViewModel) {
    var url by remember { mutableStateOf(vm.api.baseUrl) }
    var saved by remember { mutableStateOf(false) }
    Column(Modifier.fillMaxSize().padding(16.dp)) {
        Text("BrickIndex", style = MaterialTheme.typography.headlineMedium)
        Text(
            "Каталог личной коллекции LEGO® Technic с распознаванием " +
                "по фото и параметрическим поиском.\n\n" +
                "Распознавание: retrieval-архитектура, эмбеддер DINOv3 (ViT-B/16, " +
                "Meta AI), индекс FAISS по рендерам LDraw.\n\n" +
                "Приложение не связано с LEGO Group и не одобрено ею. " +
                "LEGO® — товарный знак LEGO Group.\n\n" +
                "Данные каталога: Rebrickable. 3D-модели: LDraw.org.",
            Modifier.padding(vertical = 12.dp),
        )
        OutlinedTextField(
            url, { url = it; saved = false },
            label = { Text("Адрес сервера (http://IP:8000)") },
        )
        Button(
            onClick = { vm.api.baseUrl = url; saved = true },
            modifier = Modifier.padding(top = 8.dp),
        ) { Text(if (saved) "Сохранено" else "Сохранить") }
    }
}
