import java.net.URI
import java.security.MessageDigest

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
}

// ---------------------------------------------------------------
// Backends
// ---------------------------------------------------------------

val productionApiUrl = "https://debate-coach-backend-7uc4kfztqq-uc.a.run.app"
val productionWebsiteUrl = "https://web-debate-coach1.vercel.app"

// The local build talks to a backend on your LAN. Override with
// -PlocalApiUrl=http://<your-computer's-LAN-IP>:8000 (and
// -PlocalWebsiteUrl=... for share links), or in ~/.gradle/gradle.properties.
val localApiUrl = (findProperty("localApiUrl") as String?) ?: "http://192.168.1.100:8000"
val localWebsiteUrl = (findProperty("localWebsiteUrl") as String?) ?: localApiUrl.replace(":8000", ":3000")

// Mirrors the website's NEXT_PUBLIC_VIDEO_ANALYSIS_ENABLED, which must
// match the backend's VIDEO_ANALYSIS_ENABLED (on in production). Build
// with -PproductionVideoAnalysis=false if the backend ever turns it off.
val productionVideoAnalysis = (findProperty("productionVideoAnalysis") as String?)?.toBoolean() ?: true
val localVideoAnalysis = (findProperty("localVideoAnalysis") as String?)?.toBoolean() ?: true

// -PsideBySide=true: a separate app id and name ("Debate Coach (new)"),
// so this build installs next to the one already on the phone and the
// two can be compared. Off by default: the real app id stays the same.
val sideBySide = (findProperty("sideBySide") as String?)?.toBoolean() ?: false
val appNameSuffix = if (sideBySide) " (new)" else ""

android {
    namespace = "com.debatecoach.app"
    compileSdk = 37

    defaultConfig {
        applicationId = "com.debatecoach.app"
        minSdk = 26
        targetSdk = 37
        versionCode = 2
        versionName = "1.1.0"
        if (sideBySide) applicationIdSuffix = ".redesign"
        // debatecoach://sessions, /session/<id>, /record, /progress, /insights, /account
        val scheme = if (sideBySide) "debatecoach-new" else "debatecoach"
        manifestPlaceholders["deepLinkScheme"] = scheme
        buildConfigField("String", "DEEP_LINK_SCHEME", "\"$scheme\"")
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        buildConfigField("String", "MEDIAPIPE_VERSION", "\"${libs.versions.mediapipe.get()}\"")
    }

    flavorDimensions += "backend"
    productFlavors {
        create("local") {
            dimension = "backend"
            applicationIdSuffix = ".local"
            versionNameSuffix = "-local"
            buildConfigField("String", "API_BASE_URL", "\"$localApiUrl\"")
            buildConfigField("String", "WEBSITE_URL", "\"$localWebsiteUrl\"")
            buildConfigField("boolean", "VIDEO_ANALYSIS_ENABLED", "$localVideoAnalysis")
            resValue("string", "app_name", "Debate Coach (local)$appNameSuffix")
        }
        create("production") {
            dimension = "backend"
            buildConfigField("String", "API_BASE_URL", "\"$productionApiUrl\"")
            buildConfigField("String", "WEBSITE_URL", "\"$productionWebsiteUrl\"")
            buildConfigField("boolean", "VIDEO_ANALYSIS_ENABLED", "$productionVideoAnalysis")
            resValue("string", "app_name", "Debate Coach$appNameSuffix")
        }
    }

    buildTypes {
        debug {
            isMinifyEnabled = false
        }
        release {
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        compose = true
        buildConfig = true
        resValues = true
    }

    testOptions {
        unitTests {
            isIncludeAndroidResources = true
            all { test ->
                test.maxHeapSize = "3g"
                test.systemProperty("robolectric.logging", "stdout")
                // ./gradlew :app:testLocalDebugUnitTest --tests '*Screenshots*' -PscreenshotsDir=/some/dir
                test.systemProperty("screenshots.dir", (findProperty("screenshotsDir") as String?) ?: "")
            }
        }
    }

    // One APK per processor family (smaller downloads, and armeabi-v7a
    // for older 32-bit phones), plus a universal one that runs anywhere.
    splits {
        abi {
            isEnable = true
            reset()
            include("arm64-v8a", "armeabi-v7a", "x86_64")
            isUniversalApk = true
        }
    }

    packaging {
        resources.excludes += setOf("META-INF/{AL2.0,LGPL2.1}", "META-INF/LICENSE*", "META-INF/NOTICE*")
    }

    // The .task models are stored as-is (MediaPipe memory-maps them).
    androidResources {
        noCompress += "task"
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
        optIn.addAll(
            "androidx.compose.material3.ExperimentalMaterial3Api",
            "kotlinx.serialization.ExperimentalSerializationApi",
        )
    }
}

// ---------------------------------------------------------------
// MediaPipe models: the exact files the website uses (same URLs,
// same SHA-256 as web/public/mediapipe/manifest.json), so the
// track's source.models provenance is identical. Copied from the
// website's staged copy when present, else downloaded and verified.
// ---------------------------------------------------------------

abstract class FetchMediaPipeModels : DefaultTask() {
    @get:OutputDirectory
    abstract val outputDir: DirectoryProperty

    @get:Internal
    abstract val webModelsDir: DirectoryProperty

    private val models = listOf(
        Triple(
            "face_landmarker.task",
            "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
            "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff",
        ),
        Triple(
            "hand_landmarker.task",
            "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task",
            "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1",
        ),
    )

    private fun sha256(bytes: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }

    @TaskAction
    fun fetch() {
        val dir = outputDir.get().asFile.resolve("mediapipe")
        dir.mkdirs()
        for ((name, url, expected) in models) {
            val target = dir.resolve(name)
            if (target.exists() && sha256(target.readBytes()) == expected) continue
            val staged = webModelsDir.get().asFile.resolve(name)
            val bytes = if (staged.exists() && sha256(staged.readBytes()) == expected) {
                staged.readBytes()
            } else {
                logger.lifecycle("Downloading $name")
                URI(url).toURL().openStream().use { it.readBytes() }
            }
            val actual = sha256(bytes)
            check(actual == expected) { "$name has SHA-256 $actual, expected $expected. Not using it." }
            target.writeBytes(bytes)
        }
    }
}

val fetchMediaPipeModels = tasks.register<FetchMediaPipeModels>("fetchMediaPipeModels") {
    outputDir.set(layout.buildDirectory.dir("generated/mediapipe-assets"))
    webModelsDir.set(rootProject.layout.projectDirectory.dir("../web/public/mediapipe/models"))
}

androidComponents {
    onVariants { variant ->
        variant.sources.assets?.addGeneratedSourceDirectory(fetchMediaPipeModels, FetchMediaPipeModels::outputDir)
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.lifecycle.process)
    implementation(libs.androidx.navigation.compose)
    implementation(libs.androidx.browser)

    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.ui.graphics)
    implementation(libs.compose.ui.tooling.preview)
    implementation(libs.compose.material3)
    debugImplementation(libs.compose.ui.tooling)
    debugImplementation(libs.compose.ui.test.manifest)

    implementation(libs.kotlinx.serialization.json)
    implementation(libs.kotlinx.coroutines.android)
    implementation(libs.retrofit)
    implementation(libs.retrofit.kotlinx.serialization)
    implementation(libs.okhttp)

    implementation(libs.camera.core)
    implementation(libs.camera.camera2)
    implementation(libs.camera.lifecycle)
    implementation(libs.camera.view)
    implementation(libs.mediapipe.tasks.vision)
    implementation(libs.media3.exoplayer)

    testImplementation(libs.junit)
    testImplementation(libs.kotlinx.coroutines.test)
    testImplementation(libs.turbine)
    testImplementation(libs.okhttp.mockwebserver)
    testImplementation(libs.robolectric)
    testImplementation(libs.androidx.test.core)
    testImplementation(libs.androidx.test.junit)
    testImplementation(platform(libs.compose.bom))
    testImplementation(libs.compose.ui.test.junit4)
}
